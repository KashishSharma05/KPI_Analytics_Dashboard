"""Shared helpers for the dashboard pages: data loading, filters and KPI maths."""

import json
import os

import pandas as pd
import streamlit as st

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(APP_DIR)
DATA_DIR = os.path.join(APP_DIR, "data")

# Link to the source code, shown on the home page. Left empty until the repository is public.
GITHUB_URL = ""

# Columns to read as dates in each summary file.
DATE_COLUMNS = {
    "daily": ["date_key"],
    "monthly_state": ["month_start"],
    "monthly_category_state": ["month_start"],
    "monthly_payment_state": ["month_start"],
    "anomalies": ["anomaly_date"],
    "anomaly_drivers": ["anomaly_date"],
    "cohort_retention": ["cohort_month"],
    "review_themes": ["order_date"],
}

KPI_LABELS = {
    "revenue": "Revenue (R$)",
    "orders": "Orders",
    "aov": "Average order value (R$)",
    "late_delivery_rate": "Late delivery rate (%)",
    "avg_review_score": "Average review score",
}

BLUE, RED, ORANGE, GREY = "#2563eb", "#dc2626", "#f59e0b", "#94a3b8"


@st.cache_data
def load(name):
    """Read one summary table from app/data (cached, so it is read only once)."""
    return pd.read_csv(os.path.join(DATA_DIR, f"{name}.csv"), parse_dates=DATE_COLUMNS[name])


@st.cache_data
def load_json(name):
    """Read one JSON file from app/data."""
    with open(os.path.join(DATA_DIR, f"{name}.json"), encoding="utf-8") as json_file:
        return json.load(json_file)


def result_table(item):
    """Turn the saved columns and rows of a query result into a DataFrame."""
    return pd.DataFrame(item["rows"], columns=item["columns"])


def month_filter():
    """Sidebar slider to pick a range of months. The choice is kept across pages."""
    months = sorted(load("monthly_state")["month_start"].unique())
    labels = [pd.Timestamp(m).strftime("%b %Y") for m in months]
    start_label, end_label = st.sidebar.select_slider(
        "Period", options=labels, value=st.session_state.get("period", (labels[0], labels[-1])), key="period"
    )
    start = pd.Timestamp(months[labels.index(start_label)])
    end = pd.Timestamp(months[labels.index(end_label)]) + pd.offsets.MonthEnd(0)
    return start, end


def state_filter():
    """Sidebar multiselect for customer states. Empty means all states."""
    states = sorted(load("monthly_state")["customer_state"].unique())
    return st.sidebar.multiselect("Customer state", states, key="states", placeholder="All states")


def add_kpis(df):
    """Turn the count and sum columns into KPI columns.

    Works on any grouped table, because rates and averages are calculated
    AFTER adding up the counts. (Averaging monthly averages would be wrong:
    a month with 800 orders would weigh the same as one with 7,000.)
    """
    df = df.copy()
    df["aov"] = df["revenue"] / df["delivered_orders"].where(df["delivered_orders"] > 0)
    df["late_delivery_rate"] = 100 * df["late_orders"] / df["orders_with_delivery_date"].where(df["orders_with_delivery_date"] > 0)
    df["avg_delivery_days"] = df["delivery_days_sum"] / df["orders_with_delivery_date"].where(df["orders_with_delivery_date"] > 0)
    df["avg_review_score"] = df["review_score_sum"] / df["reviews"].where(df["reviews"] > 0)
    if "canceled_orders" in df:
        df["cancellation_rate"] = 100 * df["canceled_orders"] / df["orders"].where(df["orders"] > 0)
    return df


def total_kpis(df):
    """KPIs for a whole table as one row (a pandas Series)."""
    totals = df.select_dtypes("number").sum().to_frame().T
    return add_kpis(totals).iloc[0]


def money(value):
    """R$ 1,234,567 -> 'R$ 1.23M'."""
    if pd.isna(value):
        return "-"
    if abs(value) >= 1_000_000:
        return f"R$ {value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"R$ {value / 1_000:.1f}K"
    return f"R$ {value:,.2f}"


def percent_change(now, before):
    """Change from 'before' to 'now' in percent, or None when it cannot be calculated."""
    if pd.isna(now) or pd.isna(before) or before == 0:
        return None
    return 100 * (now - before) / before
