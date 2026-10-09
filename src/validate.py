"""Data quality report for the raw schema.

Run with:  python -m src.validate

Each check is one SQL query that counts rows with a specific problem.
The report only describes the data; it does not change anything.
"""

import pandas as pd

from src.db import get_engine

pd.set_option("display.width", 200)
pd.set_option("display.max_rows", 100)

TABLES = [
    "customers",
    "sellers",
    "category_translation",
    "products",
    "orders",
    "order_items",
    "order_payments",
    "order_reviews",
]

# Each check: (what it looks for, SQL that returns one number called "issues")
CHECKS = [
    # ---- duplicates ----
    (
        "review_id values used more than once",
        """SELECT COUNT(*) AS issues FROM (
               SELECT review_id FROM raw.order_reviews GROUP BY review_id HAVING COUNT(*) > 1
           ) AS d""",
    ),
    (
        "orders that have more than one review",
        """SELECT COUNT(*) AS issues FROM (
               SELECT order_id FROM raw.order_reviews GROUP BY order_id HAVING COUNT(*) > 1
           ) AS d""",
    ),
    # ---- missing related rows ----
    (
        "orders with no items",
        """SELECT COUNT(*) AS issues FROM raw.orders o
           LEFT JOIN raw.order_items i ON i.order_id = o.order_id
           WHERE i.order_id IS NULL""",
    ),
    (
        "orders with no payment",
        """SELECT COUNT(*) AS issues FROM raw.orders o
           LEFT JOIN raw.order_payments p ON p.order_id = o.order_id
           WHERE p.order_id IS NULL""",
    ),
    (
        "orders with no review",
        """SELECT COUNT(*) AS issues FROM raw.orders o
           LEFT JOIN raw.order_reviews r ON r.order_id = o.order_id
           WHERE r.order_id IS NULL""",
    ),
    (
        "products with no category",
        "SELECT COUNT(*) AS issues FROM raw.products WHERE product_category_name IS NULL",
    ),
    (
        "products whose category has no English translation",
        """SELECT COUNT(*) AS issues FROM raw.products p
           LEFT JOIN raw.category_translation t ON t.product_category_name = p.product_category_name
           WHERE p.product_category_name IS NOT NULL AND t.product_category_name IS NULL""",
    ),
    # ---- dates that do not make sense ----
    (
        "delivered orders with no delivery date",
        """SELECT COUNT(*) AS issues FROM raw.orders
           WHERE order_status = 'delivered' AND order_delivered_customer_date IS NULL""",
    ),
    (
        "non-delivered orders that have a delivery date",
        """SELECT COUNT(*) AS issues FROM raw.orders
           WHERE order_status <> 'delivered' AND order_delivered_customer_date IS NOT NULL""",
    ),
    (
        "delivered to customer before purchase",
        """SELECT COUNT(*) AS issues FROM raw.orders
           WHERE order_delivered_customer_date < order_purchase_timestamp""",
    ),
    (
        "delivered to customer before handed to carrier",
        """SELECT COUNT(*) AS issues FROM raw.orders
           WHERE order_delivered_customer_date < order_delivered_carrier_date""",
    ),
    (
        "handed to carrier before purchase",
        """SELECT COUNT(*) AS issues FROM raw.orders
           WHERE order_delivered_carrier_date < order_purchase_timestamp""",
    ),
    # ---- money values that do not make sense ----
    ("items with price zero or negative", "SELECT COUNT(*) AS issues FROM raw.order_items WHERE price <= 0"),
    ("items with negative freight", "SELECT COUNT(*) AS issues FROM raw.order_items WHERE freight_value < 0"),
    ("payments with value zero or negative", "SELECT COUNT(*) AS issues FROM raw.order_payments WHERE payment_value <= 0"),
    ("payments with zero installments", "SELECT COUNT(*) AS issues FROM raw.order_payments WHERE payment_installments = 0"),
    ("payments with type 'not_defined'", "SELECT COUNT(*) AS issues FROM raw.order_payments WHERE payment_type = 'not_defined'"),
    (
        "orders where amount paid differs from items total by more than 0.05",
        """WITH items AS (
               SELECT order_id, SUM(price + freight_value) AS items_total
               FROM raw.order_items GROUP BY order_id
           ),
           paid AS (
               SELECT order_id, SUM(payment_value) AS paid_total
               FROM raw.order_payments GROUP BY order_id
           )
           SELECT COUNT(*) AS issues
           FROM items JOIN paid USING (order_id)
           WHERE ABS(items_total - paid_total) > 0.05""",
    ),
    # ---- review scores ----
    (
        "review scores outside 1 to 5",
        "SELECT COUNT(*) AS issues FROM raw.order_reviews WHERE review_score NOT BETWEEN 1 AND 5",
    ),
]


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main():
    engine = get_engine()

    section("1. ROW COUNTS")
    for table in TABLES:
        rows = pd.read_sql(f"SELECT COUNT(*) AS n FROM raw.{table}", engine)["n"][0]
        print(f"{table:22s} {rows:>9,}")

    section("2. MISSING VALUES (only columns that have any)")
    for table in TABLES:
        df = pd.read_sql(f"SELECT * FROM raw.{table}", engine)
        nulls = df.isna().sum()
        for column, count in nulls[nulls > 0].items():
            print(f"{table + '.' + column:50s} {count:>8,}  ({count / len(df):.1%})")

    section("3. QUALITY CHECKS (number of rows with the problem)")
    for description, sql in CHECKS:
        issues = pd.read_sql(sql, engine)["issues"][0]
        flag = "  " if issues == 0 else "!!"
        print(f"{flag} {description:68s} {issues:>8,}")

    section("4. ORDER STATUS")
    print(
        pd.read_sql(
            """SELECT order_status, COUNT(*) AS orders,
                      ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percent
               FROM raw.orders GROUP BY order_status ORDER BY orders DESC""",
            engine,
        ).to_string(index=False)
    )

    section("5. DATE RANGE AND ORDERS PER MONTH")
    print(
        pd.read_sql(
            "SELECT MIN(order_purchase_timestamp) AS first_order, MAX(order_purchase_timestamp) AS last_order FROM raw.orders",
            engine,
        ).to_string(index=False)
    )
    print()
    print(
        pd.read_sql(
            """SELECT TO_CHAR(DATE_TRUNC('month', order_purchase_timestamp), 'YYYY-MM') AS month,
                      COUNT(*) AS orders
               FROM raw.orders GROUP BY 1 ORDER BY 1""",
            engine,
        ).to_string(index=False)
    )

    section("6. CUSTOMERS AND REVIEWS")
    print(
        pd.read_sql(
            """SELECT
                   (SELECT COUNT(*) FROM raw.customers) AS customer_ids,
                   (SELECT COUNT(DISTINCT customer_unique_id) FROM raw.customers) AS unique_people,
                   (SELECT COUNT(*) FROM raw.order_reviews WHERE review_comment_message IS NOT NULL) AS reviews_with_text""",
            engine,
        ).to_string(index=False)
    )


if __name__ == "__main__":
    main()
