"""Run the whole project pipeline with one command.

Run with:  python run_pipeline.py

Steps, in order:
  1. load CSV files into the raw schema
  2. build the clean schema
  3. build the star schema (mart)
  4. create the KPI views and cohort retention
  5. detect anomalies
  6. find the drivers of each anomaly
  7. rebuild the review themes table from the saved LLM labels
  8. create the read-only user for the AI assistant
  9. export CSV files (full tables, and summary tables for the website)
 10. build the data behind the website's "How it was built" pages
 11. build the weekly report (and email it if SMTP is set in .env)

Two AI jobs are run separately because they call the LLM many times:
  python -m src.ai.review_themes    label the review sample (only needed once)
  python -m src.ai.knowledge_base   rebuild the search index after editing knowledge/
"""

import time

from sqlalchemy import text

from src import detect_anomalies, export, load, report, showcase
from src.ai import review_themes
from src.db import get_engine, run_sql_file


def step(title):
    print(f"\n===== {title} =====")


def main():
    start = time.time()

    step("1. Load raw data")
    load.main()

    step("2. Clean")
    run_sql_file("sql/02_clean.sql")

    step("3. Star schema")
    run_sql_file("sql/03_star_schema.sql")

    step("4. KPI views and cohort retention")
    run_sql_file("sql/04_kpi_views.sql")
    run_sql_file("sql/05_cohort_retention.sql")

    step("5. Detect anomalies")
    detect_anomalies.main()

    step("6. Root cause of anomalies")
    run_sql_file("sql/06_root_cause.sql")

    step("7. Review themes")
    engine = get_engine()
    with engine.connect() as connection:
        labels_exist = connection.execute(text("SELECT to_regclass('ai.review_labels')")).scalar()
    if labels_exist:
        review_themes.build_mart_table(engine)
        print("mart.review_themes rebuilt from saved labels.")
    else:
        print("No labels yet. Run: python -m src.ai.review_themes")

    step("8. Read-only user")
    run_sql_file("sql/07_readonly_role.sql")

    step("9. Export")
    export.main()

    step("10. Website data")
    showcase.main()

    step("11. Weekly report")
    report.main()

    print(f"\nPipeline finished in {time.time() - start:.1f} seconds.")


if __name__ == "__main__":
    main()
