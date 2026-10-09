"""Cross-check: does the SQL KPI layer give the same numbers as Pandas?

Run with:  python -m src.crosscheck

Monthly revenue and order counts are calculated a second time, straight
from the original CSV files with Pandas, without using any of the SQL
tables. If both routes agree, the SQL pipeline (load, clean, star schema,
views) has not lost or double-counted anything.
"""

import pandas as pd

from src.db import get_engine

RAW_DIR = "data/raw"


def monthly_from_csv():
    """Monthly orders and revenue calculated only with Pandas."""
    orders = pd.read_csv(f"{RAW_DIR}/olist_orders_dataset.csv", parse_dates=["order_purchase_timestamp"])
    items = pd.read_csv(f"{RAW_DIR}/olist_order_items_dataset.csv")

    # Same analysis window as the SQL layer: Jan 2017 to Aug 2018.
    in_window = (orders["order_purchase_timestamp"] >= "2017-01-01") & (orders["order_purchase_timestamp"] < "2018-09-01")
    orders = orders[in_window].copy()
    orders["year_month"] = orders["order_purchase_timestamp"].dt.strftime("%Y-%m")

    # Revenue per order = sum of (price + freight) of its items.
    items["item_total"] = items["price"] + items["freight_value"]
    revenue_per_order = items.groupby("order_id")["item_total"].sum()

    delivered = orders[orders["order_status"] == "delivered"].copy()
    delivered["order_revenue"] = delivered["order_id"].map(revenue_per_order).fillna(0)

    result = pd.DataFrame(
        {
            "orders_pandas": orders.groupby("year_month").size(),
            "revenue_pandas": delivered.groupby("year_month")["order_revenue"].sum().round(2),
        }
    )
    return result.reset_index()


def monthly_from_sql():
    """Monthly orders and revenue from the SQL KPI view."""
    sql = "SELECT year_month, orders AS orders_sql, revenue AS revenue_sql FROM mart.kpi_monthly ORDER BY year_month"
    df = pd.read_sql(sql, get_engine())
    df["revenue_sql"] = df["revenue_sql"].astype(float).round(2)
    return df


def main():
    comparison = monthly_from_sql().merge(monthly_from_csv(), on="year_month", how="outer")
    comparison["orders_match"] = comparison["orders_sql"] == comparison["orders_pandas"]
    # Allow one cent of difference for decimal rounding.
    comparison["revenue_match"] = (comparison["revenue_sql"] - comparison["revenue_pandas"]).abs() < 0.01

    print(comparison.to_string(index=False))
    print()
    print(f"Total revenue (SQL)   : {comparison['revenue_sql'].sum():,.2f}")
    print(f"Total revenue (Pandas): {comparison['revenue_pandas'].sum():,.2f}")

    if comparison["orders_match"].all() and comparison["revenue_match"].all():
        print("\nPASS: SQL and Pandas agree for every month.")
    else:
        print("\nFAIL: SQL and Pandas disagree. Check the rows marked False above.")


if __name__ == "__main__":
    main()
