"""Shared helpers for the dashboard pages: data loading, filters and KPI maths."""

import json
import os

import pandas as pd
import streamlit as st

APP_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(APP_DIR)
DATA_DIR = os.path.join(APP_DIR, "data")

# Link to the source code, shown on the home page.
GITHUB_URL = "https://github.com/KashishSharma05/KPI_Analytics_Dashboard"

# Columns to read as dates in each summary file.
DATE_COLUMNS = {
    "daily": ["date_key"],
    "monthly_state": ["month_start"],
    "monthly_category_state": ["month_start"],
    "monthly_payment_state": ["month_start"],
    "funnel_monthly": ["month_start"],
    "customer_monthly": ["month_start"],
    "repeat_by_first_category": [],
    "customer_value": [],
    "second_order_gap": [],
    "impact_inputs": [],
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
TEAL, NAVY = "#0d9488", "#1e3a8a"
PALETTE = [BLUE, TEAL, ORANGE, RED, "#7c3aed", GREY]

# Page styling: KPI numbers and charts sit in white tiles on a grey canvas,
# and each report page starts with a coloured header band.
STYLE = """
<style>
.block-container { padding-top: 4.2rem; }
[data-testid="stMetric"] {
    background: #ffffff; border: 1px solid #e5e7eb; border-radius: 8px;
    padding: 14px 16px; box-shadow: 0 1px 2px rgba(16, 24, 40, 0.06);
}
[data-testid="stMetricLabel"] { color: #6b7280; }
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * { font-size: 1.4rem !important; }
[data-testid="stMetricDelta"] { font-size: 0.78rem; }
[data-testid="stVerticalBlockBorderWrapper"] {
    background: #ffffff; border-radius: 8px; box-shadow: 0 1px 2px rgba(16, 24, 40, 0.06);
}
.report-header {
    background: #1e3a8a; color: #ffffff; padding: 14px 22px; border-radius: 8px;
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px;
}
.report-header .title { font-size: 1.35rem; font-weight: 700; }
.report-header .subtitle { font-size: 0.85rem; opacity: 0.85; }
.report-header .right { font-size: 0.85rem; text-align: right; opacity: 0.9; }
.tile-title { font-weight: 600; color: #374151; font-size: 0.95rem; margin-bottom: -6px; }
</style>
"""


def apply_style():
    """Add the shared CSS to the page."""
    st.markdown(STYLE, unsafe_allow_html=True)


def report_header(title, subtitle, right=""):
    """Coloured band at the top of a report page."""
    st.markdown(
        f'''<div class="report-header">
                <div><div class="title">{title}</div><div class="subtitle">{subtitle}</div></div>
                <div class="right">{right}</div>
            </div>''',
        unsafe_allow_html=True,
    )


def chart_layout(figure, height=300):
    """Same compact look for every chart inside a tile."""
    figure.update_layout(
        height=height, margin=dict(l=8, r=8, t=8, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", y=1.12, x=0), font=dict(size=12), colorway=PALETTE,
    )
    figure.update_xaxes(showgrid=False)
    figure.update_yaxes(gridcolor="#e5e7eb", zeroline=False)
    return figure


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


def month_filter(where=None):
    """Slider to pick a range of months (in the sidebar unless another place is given).

    Streamlit forgets a widget's value when the user visits a page that does
    not show that widget. So the choice is also copied to "saved_period" and
    used as the starting value, which keeps the filter the same on every page.
    """
    where = where or st.sidebar
    months = sorted(load("monthly_state")["month_start"].unique())
    labels = [pd.Timestamp(m).strftime("%b %Y") for m in months]
    saved = st.session_state.get("saved_period", (labels[0], labels[-1]))

    start_label, end_label = where.select_slider("Period", options=labels, value=saved, key="period_widget")
    st.session_state["saved_period"] = (start_label, end_label)

    start = pd.Timestamp(months[labels.index(start_label)])
    end = pd.Timestamp(months[labels.index(end_label)]) + pd.offsets.MonthEnd(0)
    return start, end


def state_filter(where=None):
    """Multiselect for customer states. Empty means all states. Kept across pages like the period."""
    where = where or st.sidebar
    states = sorted(load("monthly_state")["customer_state"].unique())
    chosen = where.multiselect("Customer state", states, default=st.session_state.get("saved_states", []),
                               key="states_widget", placeholder="All states")
    st.session_state["saved_states"] = chosen
    return chosen


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
