"""Load the Olist CSV files into the raw schema of PostgreSQL.

Run with:  python -m src.load

The script rebuilds the raw schema from sql/01_raw_schema.sql and then
bulk-loads each CSV with PostgreSQL's COPY command, so it is safe to run
again and again.

Why COPY instead of INSERT: COPY streams the whole file to the database
in one command, which is many times faster than inserting row by row.
It also loads the file exactly as it is, with no changes by Python.
"""

import csv
import sys

from src.db import get_engine, run_sql_file

RAW_DIR = "data/raw"

# Tables are listed parents first, because a child table's foreign key
# needs the parent row to exist already (orders need customers, and so on).
TABLES = [
    ("customers", "olist_customers_dataset.csv"),
    ("sellers", "olist_sellers_dataset.csv"),
    ("category_translation", "product_category_name_translation.csv"),
    ("products", "olist_products_dataset.csv"),
    ("orders", "olist_orders_dataset.csv"),
    ("order_items", "olist_order_items_dataset.csv"),
    ("order_payments", "olist_order_payments_dataset.csv"),
    ("order_reviews", "olist_order_reviews_dataset.csv"),
]

# Review comments can be long; allow the csv module to read them.
csv.field_size_limit(sys.maxsize)


def count_csv_rows(path):
    """Count data rows in a CSV (not lines: a review comment can contain line breaks)."""
    with open(path, newline="", encoding="utf-8") as csv_file:
        reader = csv.reader(csv_file)
        next(reader)  # skip the header row
        return sum(1 for _ in reader)


def copy_csv(connection, table_name, path):
    """Bulk-load one CSV into raw.<table_name>; return the number of rows loaded."""
    # HEADER true skips the first line. In CSV format an empty field becomes NULL.
    copy_sql = f"COPY raw.{table_name} FROM STDIN WITH (FORMAT csv, HEADER true)"
    with open(path, encoding="utf-8") as csv_file, connection.cursor() as cursor:
        cursor.copy_expert(copy_sql, csv_file)
        return cursor.rowcount


def main():
    print("Rebuilding raw schema...")
    run_sql_file("sql/01_raw_schema.sql")

    # COPY needs the low-level database connection, not the SQLAlchemy one.
    connection = get_engine().raw_connection()
    all_match = True
    try:
        for table_name, csv_file in TABLES:
            path = f"{RAW_DIR}/{csv_file}"
            csv_rows = count_csv_rows(path)
            table_rows = copy_csv(connection, table_name, path)
            status = "OK" if csv_rows == table_rows else "MISMATCH"
            all_match = all_match and csv_rows == table_rows
            print(f"{table_name:22s} csv rows = {csv_rows:>8,}   loaded = {table_rows:>8,}   {status}")

        # Save only if every table matched; otherwise undo the whole load.
        if all_match:
            connection.commit()
            print("\nAll tables loaded correctly.")
        else:
            connection.rollback()
            print("\nRow counts do not match. Nothing was saved.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
