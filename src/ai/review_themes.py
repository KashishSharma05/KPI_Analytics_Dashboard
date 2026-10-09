"""Classify customer review comments into complaint themes with an LLM.

Run with:  python -m src.ai.review_themes            (full sample)
           python -m src.ai.review_themes --limit 50 (small test)

The review comments are free text in Portuguese. For each one the LLM returns:
  theme           one value from a FIXED list (so results can be counted and charted)
  sentiment       positive / neutral / negative
  english_summary a short English version of the comment

Not every review is sent. A fixed sample is taken, weighted towards low
scores, because complaints are what the business needs to understand:
  2,000 reviews with 1-2 stars, 500 with 3 stars, 500 with 4-5 stars.
The sample is chosen by md5(order_id), so it is random but always the same.

Results are saved in ai.review_labels, which is kept when the mart schema
is rebuilt. Reviews already labelled are skipped, so the job can be stopped
and started again.
"""

import sys

import pandas as pd
from sqlalchemy import text

from src.ai.llm import ask, ensure_cache_table
from src.db import get_engine

THEMES = [
    "late_delivery",          # arrived late or is still on the way after the promised date
    "not_received",           # customer says the order never arrived
    "wrong_or_missing_item",  # different product, or only part of the order arrived
    "damaged_or_defective",   # broken, faulty, does not work
    "poor_quality",           # works, but worse than expected or not as described
    "seller_or_service",      # no reply, refund/return/cancellation trouble
    "positive",               # happy customer, no complaint
    "other",                  # anything that fits none of the above
]
SENTIMENTS = ["positive", "neutral", "negative"]

BATCH_SIZE = 50  # reviews per LLM call (fewer calls = stays inside the daily free limit)

SAMPLE_SQL = """
WITH candidates AS (
    SELECT
        r.order_id,
        r.review_score,
        r.review_comment_message,
        CASE WHEN r.review_score <= 2 THEN 'low'
             WHEN r.review_score = 3  THEN 'mid'
             ELSE 'high' END AS score_group,
        ROW_NUMBER() OVER (
            PARTITION BY CASE WHEN r.review_score <= 2 THEN 'low'
                              WHEN r.review_score = 3  THEN 'mid'
                              ELSE 'high' END
            ORDER BY md5(r.order_id)
        ) AS pick_order
    FROM clean.order_reviews AS r
    JOIN clean.orders AS o ON o.order_id = r.order_id
    WHERE r.review_comment_message IS NOT NULL
      AND LENGTH(r.review_comment_message) >= 5
      AND o.in_analysis_window
)
SELECT order_id, review_score, review_comment_message
FROM candidates
WHERE (score_group = 'low'  AND pick_order <= 2000)
   OR (score_group = 'mid'  AND pick_order <= 500)
   OR (score_group = 'high' AND pick_order <= 500)
ORDER BY md5(order_id)
"""

PROMPT = """You are labelling customer reviews from a Brazilian online marketplace.
The reviews are in Portuguese. Store and brand names were replaced by
Game of Thrones house names (lannister, targaryen, stark...) - ignore them.

For EACH review return one JSON object with:
  "id": the review id exactly as given
  "theme": exactly one of {themes}
  "sentiment": exactly one of {sentiments}
  "english_summary": the review in plain English, at most 20 words

How to choose the theme (pick the MAIN problem):
- late_delivery: arrived late, or still waiting after the promised date
- not_received: says the order did not arrive at all (no mention of it being merely late)
- wrong_or_missing_item: wrong product, or only part of the order came
- damaged_or_defective: broken, faulty, does not work
- poor_quality: works but worse than expected / not as described / looks fake
- seller_or_service: no answer from seller, problems with refund, return or cancellation
- positive: satisfied, no complaint
- other: none of the above

Return a JSON array with exactly {count} objects, one per review, and nothing else.

Reviews:
{reviews}
"""


def ensure_labels_table(engine):
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS ai"))
        connection.execute(
            text(
                """CREATE TABLE IF NOT EXISTS ai.review_labels (
                       order_id        VARCHAR(32) PRIMARY KEY,
                       theme           TEXT NOT NULL,
                       sentiment       TEXT NOT NULL,
                       english_summary TEXT,
                       labelled_at     TIMESTAMP NOT NULL DEFAULT NOW()
                   )"""
            )
        )


def label_batch(batch):
    """Send one batch of reviews to the LLM and return a list of clean label rows."""
    review_lines = "\n".join(
        f'[id: {row.order_id}] (score {row.review_score}) {" ".join(row.review_comment_message.split())}'
        for row in batch.itertuples()
    )
    prompt = PROMPT.format(themes=THEMES, sentiments=SENTIMENTS, count=len(batch), reviews=review_lines)
    answers = ask(prompt, as_json=True)

    # Never trust the LLM output blindly: keep only ids we actually sent,
    # and force theme / sentiment back into the allowed lists.
    sent_ids = set(batch["order_id"])
    rows = []
    for answer in answers:
        if not isinstance(answer, dict) or answer.get("id") not in sent_ids:
            continue
        rows.append(
            {
                "order_id": answer["id"],
                "theme": answer.get("theme") if answer.get("theme") in THEMES else "other",
                "sentiment": answer.get("sentiment") if answer.get("sentiment") in SENTIMENTS else "neutral",
                "english_summary": str(answer.get("english_summary", ""))[:300],
            }
        )
    return rows


def save_labels(engine, rows):
    with engine.begin() as connection:
        connection.execute(
            text(
                """INSERT INTO ai.review_labels (order_id, theme, sentiment, english_summary)
                   VALUES (:order_id, :theme, :sentiment, :english_summary)
                   ON CONFLICT (order_id) DO NOTHING"""
            ),
            rows,
        )


def build_mart_table(engine):
    """mart.review_themes = labels joined with the order facts, for the dashboard."""
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS mart.review_themes"))
        connection.execute(
            text(
                """CREATE TABLE mart.review_themes AS
                   SELECT
                       l.order_id,
                       f.order_date,
                       f.review_score,
                       l.theme,
                       l.sentiment,
                       l.english_summary,
                       f.is_late,
                       f.delivery_days,
                       c.customer_state
                   FROM ai.review_labels AS l
                   JOIN mart.fact_orders AS f ON f.order_id = l.order_id
                   JOIN mart.dim_customer AS c ON c.customer_id = f.customer_id"""
            )
        )
        connection.execute(text("ALTER TABLE mart.review_themes ADD PRIMARY KEY (order_id)"))


def main():
    limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None

    engine = get_engine()
    ensure_cache_table()
    ensure_labels_table(engine)

    sample = pd.read_sql(SAMPLE_SQL, engine)
    done = set(pd.read_sql("SELECT order_id FROM ai.review_labels", engine)["order_id"])
    todo = sample[~sample["order_id"].isin(done)]
    if limit:
        todo = todo.head(limit)
    print(f"Sample: {len(sample):,} reviews | already labelled: {len(done):,} | to do now: {len(todo):,}")

    for start in range(0, len(todo), BATCH_SIZE):
        batch = todo.iloc[start : start + BATCH_SIZE]
        rows = label_batch(batch)
        if rows:
            save_labels(engine, rows)
        print(f"  batch {start // BATCH_SIZE + 1}: sent {len(batch)}, saved {len(rows)}", flush=True)

    build_mart_table(engine)
    total = pd.read_sql("SELECT COUNT(*) AS n FROM mart.review_themes", engine)["n"][0]
    print(f"\nmart.review_themes rebuilt with {total:,} labelled reviews.")


if __name__ == "__main__":
    main()
