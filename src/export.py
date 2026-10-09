"""Export the mart tables and views to CSV files for Power BI.

Run with:  python -m src.export

Power BI reads the files in data/exports/. The star schema tables
(dim_* and fact_*) form the data model; the other files are ready-made
KPI tables for specific visuals.
"""

import os

from sqlalchemy import text

from src.db import get_engine

EXPORT_DIR = "data/exports"

# Tables and views in the mart schema to export. Ones that do not exist
# yet (built in a later phase) are skipped.
EXPORTS = [
    "dim_date",
    "dim_customer",
    "dim_product",
    "dim_seller",
    "fact_orders",
    "fact_order_items",
    "kpi_daily",
    "kpi_weekly",
    "kpi_monthly",
    "kpi_monthly_by_category",
    "kpi_monthly_by_state",
    "kpi_monthly_by_payment_type",
    "cohort_retention",
    "anomalies",
    "anomaly_drivers",
    "review_themes",
]


def main():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    engine = get_engine()

    with engine.connect() as connection:
        existing = [
            name
            for name in EXPORTS
            if connection.execute(text("SELECT to_regclass(:name)"), {"name": f"mart.{name}"}).scalar()
        ]

    # COPY ... TO STDOUT writes a whole query result as CSV in one command.
    raw_connection = engine.raw_connection()
    try:
        with raw_connection.cursor() as cursor:
            for name in existing:
                path = f"{EXPORT_DIR}/{name}.csv"
                with open(path, "w", encoding="utf-8", newline="") as csv_file:
                    cursor.copy_expert(f"COPY (SELECT * FROM mart.{name}) TO STDOUT WITH (FORMAT csv, HEADER true)", csv_file)
                print(f"{name:30s} {cursor.rowcount:>8,} rows  ->  {path}")
    finally:
        raw_connection.close()

    skipped = [name for name in EXPORTS if name not in existing]
    if skipped:
        print("\nNot built yet, skipped:", ", ".join(skipped))


if __name__ == "__main__":
    main()
