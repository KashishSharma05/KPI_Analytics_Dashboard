"""Run the whole project pipeline with one command.

Run with:  python run_pipeline.py

Steps, in order:
  1. load CSV files into the raw schema
  2. build the clean schema
  3. build the star schema (mart)
  4. create the KPI views and cohort retention
  5. detect anomalies
  6. find the drivers of each anomaly
  7. create the read-only user for the AI assistant
  8. export CSV files for Power BI
"""

import time

from src import detect_anomalies, export, load
from src.db import run_sql_file


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

    step("7. Read-only user")
    run_sql_file("sql/07_readonly_role.sql")

    step("8. Export for Power BI")
    export.main()

    print(f"\nPipeline finished in {time.time() - start:.1f} seconds.")


if __name__ == "__main__":
    main()
