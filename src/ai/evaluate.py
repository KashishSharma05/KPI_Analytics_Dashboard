"""Measure how accurate the AI features are.

  python -m src.ai.evaluate sql       text-to-SQL accuracy, with and without RAG
  python -m src.ai.evaluate reviews   review theme accuracy against hand labels

Text-to-SQL ("execution accuracy")
  Each test question has a hand-written correct query. The assistant's query
  and the correct query are both run; the answer counts as correct only if
  the two results contain the same rows. Comparing RESULTS, not SQL text,
  is fair: two differently written queries can both be right.

  The test runs twice: with RAG (rules + examples retrieved) and without
  (only table and column names). The gap shows what retrieval adds.
  None of the test questions is among the examples in the knowledge base.
"""

import json
import sys
from datetime import date, datetime
from decimal import Decimal

import pandas as pd

from src.ai.sql_guard import check_sql, get_allowed_tables, run_readonly
from src.ai.text_to_sql import answer_question
from src.db import get_engine


def normalise(value):
    """Make values comparable: numbers rounded to 2 decimals, dates as text."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return round(float(value), 2)
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return str(value).strip()


def values_match(a, b):
    """Equal values, or the same month written two ways ('2018-01' and '2018-01-01')."""
    if a == b:
        return True
    if isinstance(a, str) and isinstance(b, str) and len(a) >= 7 and len(b) >= 7 and a[:4].isdigit():
        short, long = sorted([a, b], key=len)
        return long == short + "-01"
    return False


def row_covers(generated_row, expected_row):
    """True if every expected value appears in the generated row (extra columns are allowed)."""
    remaining = list(generated_row)
    for expected_value in expected_row:
        match = next((value for value in remaining if values_match(value, expected_value)), "no match")
        if match == "no match":
            return False
        remaining.remove(match)
    return True


def same_result(generated, expected):
    """Same number of rows, and every expected row is matched by a different generated row."""
    if generated is None or len(generated) != len(expected):
        return False
    generated_rows = [[normalise(v) for v in row] for row in generated.itertuples(index=False)]
    expected_rows = [[normalise(v) for v in row] for row in expected.itertuples(index=False)]
    for expected_row in expected_rows:
        match = next((row for row in generated_rows if row_covers(row, expected_row)), None)
        if match is None:
            return False
        generated_rows.remove(match)
    return True


def evaluate_sql():
    with open("eval/golden_questions.json", encoding="utf-8") as questions_file:
        questions = json.load(questions_file)
    allowed_tables = get_allowed_tables()

    records = []
    for item in questions:
        expected = run_readonly(check_sql(item["sql"], allowed_tables))
        record = {"id": item["id"], "level": item["level"], "question": item["question"]}
        for mode, use_rag in (("with_rag", True), ("without_rag", False)):
            result = answer_question(item["question"], use_rag=use_rag, explain=False)
            record[mode] = same_result(result["rows"], expected) if result["error"] is None else False
            record[f"{mode}_sql"] = result["sql"]
            record[f"{mode}_error"] = result["error"]
        records.append(record)
        print(f"{item['id']}  with RAG: {'ok  ' if record['with_rag'] else 'FAIL'}  "
              f"without RAG: {'ok  ' if record['without_rag'] else 'FAIL'}  {item['question'][:70]}", flush=True)

    results = pd.DataFrame(records)
    results.to_csv("eval/text_to_sql_results.csv", index=False)

    print("\nExecution accuracy")
    summary = results.groupby("level")[["with_rag", "without_rag"]].agg(["sum", "count"])
    for level in ["easy", "medium", "hard"]:
        w, n = summary.loc[level, ("with_rag", "sum")], summary.loc[level, ("with_rag", "count")]
        wo = summary.loc[level, ("without_rag", "sum")]
        print(f"  {level:7s} with RAG {w}/{n}   without RAG {wo}/{n}")
    total = len(results)
    print(f"  {'total':7s} with RAG {results['with_rag'].sum()}/{total} ({100 * results['with_rag'].mean():.0f}%)"
          f"   without RAG {results['without_rag'].sum()}/{total} ({100 * results['without_rag'].mean():.0f}%)")
    print("\nDetails saved to eval/text_to_sql_results.csv")


def evaluate_reviews():
    labels = pd.read_csv("eval/review_labels.csv", dtype=str)
    labelled = labels[labels["human_theme"].notna() & (labels["human_theme"].str.strip() != "")]
    if labelled.empty:
        print("eval/review_labels.csv has no hand labels yet. Fill the human_theme column first.")
        return

    llm = pd.read_sql("SELECT order_id, theme AS llm_theme FROM ai.review_labels", get_engine())
    merged = labelled.merge(llm, on="order_id")
    merged["human_theme"] = merged["human_theme"].str.strip()
    merged["correct"] = merged["human_theme"] == merged["llm_theme"]

    print(f"Hand-labelled reviews: {len(merged)}")
    print(f"Accuracy: {merged['correct'].sum()}/{len(merged)} ({100 * merged['correct'].mean():.1f}%)\n")
    print("Rows = human label, columns = LLM label")
    print(pd.crosstab(merged["human_theme"], merged["llm_theme"]).to_string())


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode == "sql":
        evaluate_sql()
    elif mode == "reviews":
        evaluate_reviews()
    else:
        print("Usage: python -m src.ai.evaluate sql | reviews")
