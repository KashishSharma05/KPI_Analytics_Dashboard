"""Build the files behind the "How it was built" pages of the website.

Run with:  python -m src.showcase            (SQL examples and safety test)
           python -m src.showcase --ai       (also record AI assistant examples; calls the LLM)

The deployed website has no database, so the results of a few featured
queries, the safety-check results and some recorded assistant answers are
saved as JSON in app/data/ and simply displayed.
"""

import json
import sys

import pandas as pd

from src.ai.sql_guard import SELF_TEST, UnsafeSQLError, check_sql, get_allowed_tables
from src.db import get_engine

APP_DATA_DIR = "app/data"

# Queries shown on the "Data and SQL" page: title, the business question, the SQL.
FEATURED_QUERIES = [
    {
        "title": "Month-over-month revenue growth",
        "skills": "CTE, LAG window function, NULLIF",
        "question": "How fast is revenue growing from one month to the next?",
        "sql": """WITH monthly AS (
    SELECT
        DATE_TRUNC('month', order_date)::date AS month_start,
        SUM(order_revenue)                    AS revenue
    FROM mart.fact_orders
    WHERE is_delivered AND in_analysis_window
    GROUP BY 1
)
SELECT
    TO_CHAR(month_start, 'YYYY-MM')              AS month,
    revenue,
    LAG(revenue) OVER (ORDER BY month_start)     AS previous_month,
    ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month_start))
          / NULLIF(LAG(revenue) OVER (ORDER BY month_start), 0), 1) AS growth_pct
FROM monthly
ORDER BY month_start""",
    },
    {
        "title": "Top category of each month",
        "skills": "JOIN, RANK with PARTITION BY, share of total",
        "question": "Which product category earned the most in each month, and what share of the month was it?",
        "sql": """WITH category_month AS (
    SELECT
        DATE_TRUNC('month', i.order_date)::date AS month_start,
        p.category,
        SUM(i.item_total) AS revenue
    FROM mart.fact_order_items AS i
    JOIN mart.dim_product AS p ON p.product_id = i.product_id
    WHERE i.is_delivered AND i.in_analysis_window
    GROUP BY 1, 2
),
ranked AS (
    SELECT
        month_start,
        category,
        revenue,
        ROUND(100.0 * revenue / SUM(revenue) OVER (PARTITION BY month_start), 1) AS share_pct,
        RANK() OVER (PARTITION BY month_start ORDER BY revenue DESC)           AS revenue_rank
    FROM category_month
)
SELECT TO_CHAR(month_start, 'YYYY-MM') AS month, category, revenue, share_pct
FROM ranked
WHERE revenue_rank = 1
ORDER BY month_start""",
    },
    {
        "title": "Daily revenue with a 7-day rolling average",
        "skills": "LEFT JOIN from a date dimension, window frame (ROWS BETWEEN)",
        "question": "What did Black Friday week look like against the recent trend?",
        "sql": """WITH daily AS (
    SELECT
        d.date_key,
        COUNT(f.order_id)                                               AS orders,
        COALESCE(SUM(f.order_revenue) FILTER (WHERE f.is_delivered), 0) AS revenue
    FROM mart.dim_date AS d
    LEFT JOIN mart.fact_orders AS f ON f.order_date = d.date_key
    WHERE d.in_analysis_window
    GROUP BY d.date_key
),
with_average AS (
    SELECT
        date_key,
        orders,
        revenue,
        ROUND(AVG(revenue) OVER (ORDER BY date_key ROWS BETWEEN 6 PRECEDING AND CURRENT ROW), 2) AS revenue_7d_avg
    FROM daily
)
SELECT * FROM with_average
WHERE date_key BETWEEN DATE '2017-11-20' AND DATE '2017-11-28'
ORDER BY date_key""",
    },
    {
        "title": "Where delivery is slowest",
        "skills": "FILTER aggregates, HAVING, safe division",
        "question": "Which states wait longest for delivery, and how does that show up in late rates and reviews?",
        "sql": """SELECT
    c.customer_state,
    COUNT(*)                                                                 AS delivered_orders,
    ROUND(AVG(f.delivery_days), 1)                                           AS avg_delivery_days,
    ROUND(100.0 * COUNT(*) FILTER (WHERE f.is_late) / COUNT(f.is_late), 1)   AS late_delivery_pct,
    ROUND(AVG(f.review_score), 2)                                            AS avg_review_score
FROM mart.fact_orders AS f
JOIN mart.dim_customer AS c ON c.customer_id = f.customer_id
WHERE f.is_delivered AND f.in_analysis_window
GROUP BY c.customer_state
HAVING COUNT(*) >= 500
ORDER BY avg_delivery_days DESC
LIMIT 8""",
    },
    {
        "title": "Cohort retention",
        "skills": "Chained CTEs, DISTINCT, FIRST_VALUE",
        "question": "Of customers who first bought in a given month, what percentage bought again later?",
        "sql": """WITH customer_months AS (
    SELECT DISTINCT
        c.customer_unique_id,
        DATE_TRUNC('month', f.order_date)::date AS order_month
    FROM mart.fact_orders AS f
    JOIN mart.dim_customer AS c ON c.customer_id = f.customer_id
    WHERE f.is_delivered AND f.in_analysis_window
),
first_purchase AS (
    SELECT customer_unique_id, MIN(order_month) AS cohort_month
    FROM customer_months
    GROUP BY customer_unique_id
),
cohort_activity AS (
    SELECT
        fp.cohort_month,
        ((EXTRACT(YEAR FROM cm.order_month) - EXTRACT(YEAR FROM fp.cohort_month)) * 12
          + EXTRACT(MONTH FROM cm.order_month) - EXTRACT(MONTH FROM fp.cohort_month))::int AS months_since_first,
        COUNT(*) AS active_customers
    FROM customer_months AS cm
    JOIN first_purchase AS fp ON fp.customer_unique_id = cm.customer_unique_id
    GROUP BY 1, 2
)
SELECT
    TO_CHAR(cohort_month, 'YYYY-MM') AS cohort,
    months_since_first,
    active_customers,
    ROUND(100.0 * active_customers
          / FIRST_VALUE(active_customers) OVER (PARTITION BY cohort_month ORDER BY months_since_first), 2) AS retention_pct
FROM cohort_activity
WHERE cohort_month = DATE '2017-06-01' AND months_since_first <= 5
ORDER BY months_since_first""",
    },
    {
        "title": "Root cause of an anomaly",
        "skills": "Conditional aggregation against a baseline, window total, ranking",
        "question": "On Black Friday 2017, which customer states caused the jump in revenue?",
        "sql": """WITH state_daily AS (
    SELECT
        f.order_date,
        c.customer_state,
        SUM(f.order_revenue) FILTER (WHERE f.is_delivered) AS revenue
    FROM mart.fact_orders AS f
    JOIN mart.dim_customer AS c ON c.customer_id = f.customer_id
    WHERE f.order_date BETWEEN DATE '2017-11-24' - 28 AND DATE '2017-11-24'
    GROUP BY f.order_date, c.customer_state
),
actual_vs_baseline AS (
    SELECT
        customer_state,
        COALESCE(SUM(revenue) FILTER (WHERE order_date = DATE '2017-11-24'), 0)        AS actual,
        COALESCE(SUM(revenue) FILTER (WHERE order_date < DATE '2017-11-24'), 0) / 28.0 AS baseline
    FROM state_daily
    GROUP BY customer_state
)
SELECT
    customer_state,
    ROUND(actual, 0)            AS revenue_that_day,
    ROUND(baseline, 0)          AS normal_daily_revenue,
    ROUND(actual - baseline, 0) AS change,
    ROUND(100.0 * (actual - baseline) / SUM(actual - baseline) OVER (), 1) AS share_of_change_pct
FROM actual_vs_baseline
ORDER BY change DESC
LIMIT 6""",
    },
]

# Questions recorded for the "AI assistant" page.
ASSISTANT_QUESTIONS = [
    "Which month had the highest revenue?",
    "What are the top 5 product categories by revenue?",
    "Show the late delivery rate for each month of 2018.",
    "Which 5 states have the longest average delivery time?",
    "What do customers complain about most in low-score reviews?",
    "Delete all orders from 2017",
    "What will revenue be next year?",
]


def to_records(df, limit=12):
    """First rows of a DataFrame as JSON-friendly lists (numbers as float, the rest as text)."""
    df = df.head(limit).copy()
    for column in df.columns:
        as_number = pd.to_numeric(df[column], errors="coerce")
        df[column] = as_number.astype(float).round(2) if as_number.notna().all() else df[column].astype(str)
    return {"columns": list(df.columns), "rows": df.values.tolist()}


def save(name, data):
    path = f"{APP_DATA_DIR}/{name}.json"
    with open(path, "w", encoding="utf-8") as json_file:
        json.dump(data, json_file, ensure_ascii=False, indent=1)
    print(f"  {len(data):>3} items -> {path}")


def build_sql_showcase(engine):
    showcase = []
    for query in FEATURED_QUERIES:
        result = pd.read_sql(query["sql"].replace("%", "%%"), engine)
        showcase.append({**query, "total_rows": len(result), **to_records(result)})
    save("sql_showcase", showcase)

    log = pd.read_sql("SELECT rule, rows_affected, action FROM clean.cleaning_log ORDER BY rule_no", engine)
    save("cleaning_log", log.to_dict("records"))


def build_guard_results():
    allowed_tables = get_allowed_tables()
    results = []
    for sql, should_be_allowed in SELF_TEST:
        try:
            check_sql(sql, allowed_tables)
            outcome = "allowed"
        except UnsafeSQLError as error:
            outcome = f"blocked: {error}"
        results.append({"sql": sql, "expected": "allowed" if should_be_allowed else "blocked", "outcome": outcome})
    save("guard_tests", results)


def build_assistant_examples():
    from src.ai.text_to_sql import answer_question  # imported here: needs the API key

    examples = []
    for question in ASSISTANT_QUESTIONS:
        result = answer_question(question)
        example = {"question": question, "sql": result["sql"], "answer": result["answer"],
                   "error": result["error"], "sources": result["sources"][:6]}
        if result["rows"] is not None:
            example.update(to_records(result["rows"]))
        examples.append(example)
        print(f"    {question[:60]:60s} {'ok' if result['error'] is None else 'no query'}")
    save("assistant_examples", examples)


def main():
    engine = get_engine()
    print("Building website data:")
    build_sql_showcase(engine)
    build_guard_results()
    if "--ai" in sys.argv:
        build_assistant_examples()


if __name__ == "__main__":
    main()
