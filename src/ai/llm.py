"""One place for every call to Google Gemini.

What this wrapper adds on top of the plain API call:
  - retry with a growing wait when the API is busy or rate-limited
  - a fallback model if the main model stays unavailable
  - JSON output, parsed into Python objects
  - a cache table (ai.llm_cache), so the same prompt is never paid for twice
    and an interrupted job can continue where it stopped
"""

import hashlib
import json
import os
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types
from sqlalchemy import text

from src.db import get_engine

load_dotenv()

# Models are chosen for the free tier: the "lite" models allow 500 requests a day
# and 15 a minute, while the larger Flash models allow only 20 requests a day.
# The first model is tried first; the second is used only if the first is unavailable.
MODELS = [os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite"), "gemini-3.1-flash-lite"]
EMBEDDING_MODEL = "gemini-embedding-001"
MAX_ROUNDS = 4
SECONDS_BETWEEN_CALLS = 4.5  # at most about 13 requests a minute

_client = None
_last_call_time = 0.0


def get_client():
    """Create the Gemini client once and reuse it."""
    global _client
    if _client is None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY is missing in the .env file.")
        _client = genai.Client(api_key=api_key, http_options=types.HttpOptions(timeout=120_000))
    return _client


def ensure_cache_table():
    """The cache lives in its own schema (ai) so rebuilding mart does not delete it."""
    with get_engine().begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS ai"))
        connection.execute(
            text(
                """CREATE TABLE IF NOT EXISTS ai.llm_cache (
                       prompt_hash TEXT PRIMARY KEY,
                       model       TEXT NOT NULL,
                       response    TEXT NOT NULL,
                       created_at  TIMESTAMP NOT NULL DEFAULT NOW()
                   )"""
            )
        )


def _cache_get(prompt_hash):
    with get_engine().connect() as connection:
        return connection.execute(
            text("SELECT response FROM ai.llm_cache WHERE prompt_hash = :h"), {"h": prompt_hash}
        ).scalar()


def _cache_put(prompt_hash, model, response):
    with get_engine().begin() as connection:
        connection.execute(
            text(
                """INSERT INTO ai.llm_cache (prompt_hash, model, response)
                   VALUES (:h, :m, :r) ON CONFLICT (prompt_hash) DO NOTHING"""
            ),
            {"h": prompt_hash, "m": model, "r": response},
        )


def _wait_for_rate_limit():
    """Pause so that calls are never closer together than SECONDS_BETWEEN_CALLS."""
    global _last_call_time
    wait = SECONDS_BETWEEN_CALLS - (time.time() - _last_call_time)
    if wait > 0:
        time.sleep(wait)
    _last_call_time = time.time()


def _call_with_retry(prompt, as_json):
    """Call Gemini. On a temporary error, try the other model, then wait and go round again."""
    config = types.GenerateContentConfig(
        temperature=0,  # same prompt -> same answer, as far as possible
        response_mime_type="application/json" if as_json else "text/plain",
    )
    models = list(MODELS)
    last_error = None
    for round_number in range(MAX_ROUNDS):
        for model in list(models):
            _wait_for_rate_limit()
            try:
                response = get_client().models.generate_content(model=model, contents=prompt, config=config)
                if response.text:
                    return model, response.text
                last_error = RuntimeError("empty response")
            except errors.APIError as error:
                last_error = error
                # 429 = rate limit, 5xx = server busy. Anything else will not fix itself.
                if error.code not in (429, 500, 503):
                    raise
                # Daily quota used up: stop trying this model for the rest of this call.
                if error.code == 429 and "PerDay" in str(error):
                    models.remove(model)
                print(f"    (retrying: {error.code} from {model})", flush=True)
        if not models:
            break
        time.sleep(5 * 2**round_number)  # wait 5, 10, 20, 40 seconds between rounds
    raise RuntimeError(f"Gemini call failed after retries: {last_error}")


def ask(prompt, as_json=False, use_cache=True):
    """Send a prompt to Gemini. Returns text, or parsed JSON when as_json=True."""
    prompt_hash = hashlib.sha256(f"{as_json}|{prompt}".encode("utf-8")).hexdigest()

    answer = _cache_get(prompt_hash) if use_cache else None
    if answer is None:
        model, answer = _call_with_retry(prompt, as_json)
        if use_cache:
            _cache_put(prompt_hash, model, answer)

    return json.loads(answer) if as_json else answer


def embed(texts):
    """Turn a list of texts into a list of embedding vectors (768 numbers each)."""
    vectors = []
    # The API takes a limited number of texts per call, so send them in groups.
    for start in range(0, len(texts), 50):
        batch = texts[start : start + 50]
        result = get_client().models.embed_content(
            model=EMBEDDING_MODEL,
            contents=batch,
            config=types.EmbedContentConfig(output_dimensionality=768),
        )
        vectors.extend(e.values for e in result.embeddings)
    return vectors
