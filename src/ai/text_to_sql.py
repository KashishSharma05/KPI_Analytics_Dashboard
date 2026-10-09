"""Ask-Your-Data: turn a business question in English into an answer.

Flow for every question:
  1. retrieve  - find the KPI rules, table notes and example queries that
                 are most similar to the question (RAG, see knowledge_base.py)
  2. generate  - ask the LLM to write one PostgreSQL SELECT
  3. guard     - check the SQL is a safe read-only query (sql_guard.py)
  4. run       - execute it as the read-only database user
  5. repair    - if the database returns an error, show the error to the
                 LLM once and let it fix the query
  6. explain   - ask the LLM to describe the result rows in plain English

The LLM never calculates a number itself. Every number comes from the
database; the LLM only writes the query and words the answer.

Try it:  python -m src.ai.text_to_sql "Which month had the highest revenue?"
"""

import sys

import pandas as pd

from src.ai import knowledge_base
from src.ai.llm import ask, ensure_cache_table
from src.ai.sql_guard import UnsafeSQLError, check_sql, get_allowed_tables, run_readonly
from src.db import get_engine

SQL_PROMPT = """You write PostgreSQL queries for a business analyst.

Rules:
- Return ONE SELECT statement. Never modify data.
- Use only the tables and columns listed below. Do not invent names.
- Follow the business rules exactly when they are given.
- Give result columns clear names.
- If the question cannot be answered from these tables, return null for "sql".

Tables (schema "mart"; table names need no schema prefix):
{schema}
{context}
Question: {question}
{error_feedback}
Reply as JSON: {{"sql": "<the query or null>", "reason": "<one short sentence>"}}
"""

ANSWER_PROMPT = """A business user asked: "{question}"

This SQL was run:
{sql}

Result ({row_count} rows{truncated}):
{rows}

Write a short answer for the user in 1 to 3 sentences.
Use ONLY numbers that appear in the result. Do not add facts or guesses.
Currency is Brazilian real (R$). If the result is empty, say that no data matched.
"""

_resources = {}


def get_resources():
    """Load slow things once: allowed tables, column list and the search index."""
    if not _resources:
        ensure_cache_table()
        _resources["allowed_tables"] = get_allowed_tables()
        _resources["schema"] = describe_schema()
        _resources["index"], _resources["documents"] = knowledge_base.load_index()
    return _resources


def describe_schema():
    """One line per table: name(column type, column type, ...), read from the database."""
    columns = pd.read_sql(
        """SELECT table_name, column_name, data_type
           FROM information_schema.columns
           WHERE table_schema = 'mart'
           ORDER BY table_name, ordinal_position""",
        get_engine(),
    )
    lines = []
    for table_name, group in columns.groupby("table_name"):
        column_list = ", ".join(f"{row.column_name} {row.data_type}" for row in group.itertuples())
        lines.append(f"- {table_name}({column_list})")
    return "\n".join(lines)


def build_context(question, resources):
    """Text block with the retrieved rules, table notes and examples."""
    found = knowledge_base.search(question, resources["index"], resources["documents"])
    rules = [d["text"] for d in found if d["kind"] in ("definition", "table")]
    examples = [f"Q: {d['title']}\nSQL: {d['sql']}" for d in found if d["kind"] == "example"]
    context = "\nBusiness rules and table notes:\n" + "\n".join(f"- {rule}" for rule in rules)
    context += "\n\nExamples of correct queries:\n" + "\n\n".join(examples) + "\n"
    return context, [d["title"] for d in found]


def answer_question(question, use_rag=True, explain=True):
    """Run the whole flow and return a dictionary describing what happened."""
    resources = get_resources()
    context, sources = build_context(question, resources) if use_rag else ("", [])

    result = {"question": question, "sql": None, "rows": None, "answer": None, "error": None,
              "attempts": 0, "sources": sources}

    error_feedback = ""
    for attempt in (1, 2):  # the first try, plus one repair
        result["attempts"] = attempt
        prompt = SQL_PROMPT.format(
            schema=resources["schema"], context=context, question=question, error_feedback=error_feedback
        )
        reply = ask(prompt, as_json=True)
        sql = reply.get("sql") if isinstance(reply, dict) else None

        if not sql:
            result["error"] = "The assistant could not write a query for this question."
            result["answer"] = reply.get("reason") if isinstance(reply, dict) else None
            return result

        try:
            safe_sql = check_sql(sql, resources["allowed_tables"])
            result["sql"] = safe_sql
            result["rows"] = run_readonly(safe_sql)
            result["error"] = None
            break
        except UnsafeSQLError as error:
            # A blocked query is never retried: it must not get a second chance.
            result["sql"] = sql
            result["error"] = f"Blocked by the safety check: {error}"
            return result
        except Exception as error:  # the database rejected the query
            result["sql"] = sql
            result["error"] = str(error).splitlines()[0]
            error_feedback = (
                f"\nYour previous query was:\n{sql}\n"
                f"PostgreSQL returned this error:\n{result['error']}\nFix the query.\n"
            )

    if result["error"] is None and explain:
        result["answer"] = explain_result(question, result["sql"], result["rows"])
    return result


def explain_result(question, sql, rows):
    """Ask the LLM to word the answer, using only the result rows."""
    shown = rows.head(30)
    prompt = ANSWER_PROMPT.format(
        question=question,
        sql=sql,
        row_count=len(rows),
        truncated=", first 30 shown" if len(rows) > 30 else "",
        rows=shown.to_csv(index=False),
    )
    return ask(prompt).strip()


def main():
    question = " ".join(sys.argv[1:]) or "Which month had the highest revenue?"
    result = answer_question(question)
    print("Question:", result["question"])
    print("Sources :", "; ".join(result["sources"][:6]))
    print("SQL     :", result["sql"])
    if result["error"]:
        print("Error   :", result["error"])
    else:
        print(result["rows"].head(15).to_string(index=False))
    print("Answer  :", result["answer"])


if __name__ == "__main__":
    main()
