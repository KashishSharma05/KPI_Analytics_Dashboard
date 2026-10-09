"""Export data out of the database as CSV files.

Run with:  python -m src.export

Two sets of files are written:

  data/exports/   the full star schema and KPI views, for a BI tool.
                  Large, so not stored in git.

  app/data/       small summary tables for the Streamlit dashboard.
                  Stored in git, so the deployed dashboard needs no database.
                  They hold COUNTS and SUMS (not ready-made averages or
                  rates), so the dashboard can combine any date range or
                  set of states and still get exact KPIs.
"""

import os

from sqlalchemy import text

from src.db import get_engine

EXPORT_DIR = "data/exports"
APP_DATA_DIR = "app/data"

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


# Summary tables for the dashboard: file name -> query.
APP_EXPORTS = {
    # one row per day: the building blocks of every KPI
    "daily": """
        SELECT
            d.date_key,
            d.is_complete_data,
            COUNT(f.order_id)                                               AS orders,
            COUNT(f.order_id) FILTER (WHERE f.is_delivered)                 AS delivered_orders,
            COALESCE(SUM(f.order_revenue) FILTER (WHERE f.is_delivered), 0) AS revenue,
            COUNT(f.order_id) FILTER (WHERE f.is_canceled)                  AS canceled_orders,
            COUNT(f.order_id) FILTER (WHERE f.is_late)                      AS late_orders,
            COUNT(f.is_late)                                                AS orders_with_delivery_date,
            COALESCE(SUM(f.delivery_days), 0)                               AS delivery_days_sum,
            COUNT(f.review_score)                                           AS reviews,
            COALESCE(SUM(f.review_score), 0)                                AS review_score_sum
        FROM mart.dim_date AS d
        LEFT JOIN mart.fact_orders AS f ON f.order_date = d.date_key
        WHERE d.in_analysis_window
        GROUP BY d.date_key, d.is_complete_data
        ORDER BY d.date_key""",
    # one row per month and customer state
    "monthly_state": """
        SELECT
            DATE_TRUNC('month', f.order_date)::date                         AS month_start,
            c.customer_state,
            COUNT(*)                                                        AS orders,
            COUNT(*) FILTER (WHERE f.is_delivered)                          AS delivered_orders,
            COALESCE(SUM(f.order_revenue) FILTER (WHERE f.is_delivered), 0) AS revenue,
            COUNT(*) FILTER (WHERE f.is_late)                               AS late_orders,
            COUNT(f.is_late)                                                AS orders_with_delivery_date,
            COALESCE(SUM(f.delivery_days), 0)                               AS delivery_days_sum,
            COUNT(f.review_score)                                           AS reviews,
            COALESCE(SUM(f.review_score), 0)                                AS review_score_sum
        FROM mart.fact_orders AS f
        JOIN mart.dim_customer AS c ON c.customer_id = f.customer_id
        WHERE f.in_analysis_window
        GROUP BY 1, 2
        ORDER BY 1, 2""",
    # one row per month, category and customer state (delivered orders only)
    "monthly_category_state": """
        SELECT
            DATE_TRUNC('month', i.order_date)::date AS month_start,
            p.category,
            c.customer_state,
            COUNT(DISTINCT i.order_id)              AS orders,
            COUNT(*)                                AS items_sold,
            SUM(i.item_total)                       AS revenue
        FROM mart.fact_order_items AS i
        JOIN mart.dim_product AS p ON p.product_id = i.product_id
        JOIN mart.dim_customer AS c ON c.customer_id = i.customer_id
        WHERE i.is_delivered AND i.in_analysis_window
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3""",
    # one row per month, payment type and customer state
    "monthly_payment_state": """
        SELECT
            DATE_TRUNC('month', f.order_date)::date                         AS month_start,
            f.main_payment_type,
            c.customer_state,
            COUNT(*)                                                        AS orders,
            COALESCE(SUM(f.order_revenue) FILTER (WHERE f.is_delivered), 0) AS revenue
        FROM mart.fact_orders AS f
        JOIN mart.dim_customer AS c ON c.customer_id = f.customer_id
        WHERE f.in_analysis_window
        GROUP BY 1, 2, 3
        ORDER BY 1, 2, 3""",
    # customer journey: how many orders reach each stage, per month
    "funnel_monthly": "SELECT * FROM mart.order_funnel_monthly ORDER BY month_start",
    # new vs returning customers and their revenue, per month
    "customer_monthly": "SELECT * FROM mart.customer_monthly ORDER BY month_start",
    "repeat_by_first_category": "SELECT * FROM mart.repeat_by_first_category ORDER BY repeat_rate_pct DESC",
    # customers and revenue by how many orders they placed
    "customer_value": """
        SELECT
            CASE WHEN delivered_orders = 1 THEN '1 order'
                 WHEN delivered_orders = 2 THEN '2 orders'
                 ELSE '3 or more orders' END AS orders_placed,
            COUNT(*)               AS customers,
            SUM(revenue)           AS revenue,
            ROUND(AVG(revenue), 2) AS revenue_per_customer
        FROM mart.customer_summary
        GROUP BY 1
        ORDER BY 1""",
    # how long repeat customers waited before their second order
    "second_order_gap": """
        WITH gaps AS (
            SELECT second_order_date - first_order_date AS days
            FROM mart.customer_summary
            WHERE second_order_date IS NOT NULL
        )
        SELECT
            CASE WHEN days = 0    THEN '1. Same day'
                 WHEN days <= 30  THEN '2. 1-30 days'
                 WHEN days <= 90  THEN '3. 31-90 days'
                 WHEN days <= 180 THEN '4. 91-180 days'
                 ELSE '5. Over 180 days' END AS gap,
            COUNT(*) AS customers
        FROM gaps
        GROUP BY 1
        ORDER BY 1""",
    # counts used to size the business impact of late delivery and cancellations
    "impact_inputs": """
        SELECT
            COUNT(*) FILTER (WHERE is_delivered AND is_late AND review_score IS NOT NULL)          AS late_reviewed,
            COUNT(*) FILTER (WHERE is_delivered AND is_late AND review_score <= 2)                 AS late_low_reviews,
            COUNT(*) FILTER (WHERE is_delivered AND is_late = FALSE AND review_score IS NOT NULL)  AS on_time_reviewed,
            COUNT(*) FILTER (WHERE is_delivered AND is_late = FALSE AND review_score <= 2)         AS on_time_low_reviews,
            COUNT(*) FILTER (WHERE is_canceled)                                                    AS canceled_orders,
            COALESCE(SUM(order_revenue) FILTER (WHERE is_canceled), 0)                             AS canceled_order_value
        FROM mart.fact_orders
        WHERE in_analysis_window""",
    "anomalies": "SELECT * FROM mart.anomalies ORDER BY anomaly_date, kpi",
    "anomaly_drivers": "SELECT * FROM mart.anomaly_drivers ORDER BY anomaly_date, kpi, dimension, driver_rank",
    "cohort_retention": "SELECT * FROM mart.cohort_retention ORDER BY cohort_month, months_since_first",
    "review_themes": """
        SELECT order_date, review_score, theme, sentiment, english_summary, is_late, customer_state
        FROM mart.review_themes
        ORDER BY order_date""",
}


def table_exists(connection, name):
    return connection.execute(text("SELECT to_regclass(:name)"), {"name": f"mart.{name}"}).scalar() is not None


def copy_query_to_csv(cursor, query, path):
    """COPY ... TO STDOUT writes a whole query result as CSV in one command."""
    with open(path, "w", encoding="utf-8", newline="") as csv_file:
        cursor.copy_expert(f"COPY ({query}) TO STDOUT WITH (FORMAT csv, HEADER true)", csv_file)
    return cursor.rowcount


def main():
    os.makedirs(EXPORT_DIR, exist_ok=True)
    os.makedirs(APP_DATA_DIR, exist_ok=True)
    engine = get_engine()

    with engine.connect() as connection:
        existing = [name for name in EXPORTS if table_exists(connection, name)]
        has_review_themes = table_exists(connection, "review_themes")

    raw_connection = engine.raw_connection()
    try:
        with raw_connection.cursor() as cursor:
            print("Full tables for a BI tool:")
            for name in existing:
                path = f"{EXPORT_DIR}/{name}.csv"
                rows = copy_query_to_csv(cursor, f"SELECT * FROM mart.{name}", path)
                print(f"  {name:30s} {rows:>8,} rows  ->  {path}")

            print("\nSummary tables for the dashboard:")
            for name, query in APP_EXPORTS.items():
                if name == "review_themes" and not has_review_themes:
                    continue
                path = f"{APP_DATA_DIR}/{name}.csv"
                rows = copy_query_to_csv(cursor, query, path)
                print(f"  {name:30s} {rows:>8,} rows  ->  {path}")
    finally:
        raw_connection.close()

    skipped = [name for name in EXPORTS if name not in existing]
    if skipped:
        print("\nNot built yet, skipped:", ", ".join(skipped))


if __name__ == "__main__":
    main()
