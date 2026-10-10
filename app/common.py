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

# One palette for the whole site.
INK = "#042f2e"       # deep green: sidebar and header bands
PRIMARY = "#0d9488"   # teal: main bars and lines
SKY = "#0ea5e9"       # second series
AMBER = "#f59e0b"     # warnings, late delivery
ROSE = "#e11d48"      # anomalies, bad outcomes
VIOLET = "#7c3aed"
GREY = "#94a3b8"
PALETTE = [PRIMARY, SKY, AMBER, ROSE, VIOLET, GREY]

STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
/* set on the page root only, so icon fonts inside buttons and expanders keep working */
html, body, [data-testid="stAppViewContainer"], [data-testid="stSidebar"] { font-family: 'Plus Jakarta Sans', -apple-system, sans-serif; }

.block-container { padding-top: 3.4rem; max-width: 1340px; }
h2, h3 { color: #042f2e; letter-spacing: -0.01em; }

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] { background: linear-gradient(180deg, #042f2e 0%, #115e59 100%); }
[data-testid="stSidebar"] * { color: #ccfbf1; }
[data-testid="stSidebarNavLink"] { border-radius: 10px; margin: 2px 6px; }
[data-testid="stSidebarNavLink"]:hover { background: rgba(255, 255, 255, 0.10); }
[data-testid="stSidebarNavLink"][aria-current="page"] { background: rgba(255, 255, 255, 0.18); }
[data-testid="stSidebarNavLink"][aria-current="page"] span { color: #ffffff; font-weight: 600; }
[data-testid="stSidebar"] [data-baseweb="select"] > div { background: rgba(255, 255, 255, 0.10); border-color: rgba(255, 255, 255, 0.25); }
[data-testid="stSidebar"] [data-baseweb="tag"] { background: #f59e0b; }
[data-testid="stSidebar"] [data-baseweb="tag"] * { color: #042f2e; }

/* ---------- KPI tiles: white card with a coloured top edge ---------- */
[data-testid="stMetric"] {
    background: #ffffff; border: 1px solid #e2ece9; border-top: 4px solid #0d9488; border-radius: 14px;
    padding: 14px 18px 12px 18px; box-shadow: 0 4px 14px rgba(4, 47, 46, 0.06);
}
[data-testid="stColumn"]:nth-of-type(2) [data-testid="stMetric"] { border-top-color: #f59e0b; }
[data-testid="stColumn"]:nth-of-type(3) [data-testid="stMetric"] { border-top-color: #0ea5e9; }
[data-testid="stColumn"]:nth-of-type(4) [data-testid="stMetric"] { border-top-color: #e11d48; }
[data-testid="stColumn"]:nth-of-type(5) [data-testid="stMetric"] { border-top-color: #7c3aed; }
[data-testid="stColumn"]:nth-of-type(6) [data-testid="stMetric"] { border-top-color: #84cc16; }
[data-testid="stMetricLabel"] { color: #64748b; font-weight: 500; }
[data-testid="stMetricValue"], [data-testid="stMetricValue"] * { font-size: 1.3rem !important; font-weight: 700; color: #042f2e; }
[data-testid="stMetricDelta"] { font-size: 0.78rem; }

/* ---------- chart and content cards ---------- */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: #ffffff; border-radius: 16px; border-color: #e2ece9 !important;
    box-shadow: 0 4px 14px rgba(4, 47, 46, 0.06);
}
.tile-title { font-weight: 600; color: #042f2e; font-size: 0.98rem; margin-bottom: -4px; }

/* ---------- hero on the home page ---------- */
.hero {
    background: radial-gradient(800px 320px at 90% -10%, rgba(245, 158, 11, 0.55), transparent 60%),
                linear-gradient(120deg, #042f2e 0%, #0f766e 55%, #14b8a6 100%);
    color: #ffffff; padding: 38px 40px; border-radius: 22px; margin-bottom: 20px;
    box-shadow: 0 14px 34px rgba(15, 118, 110, 0.30); position: relative; overflow: hidden;
}
.hero::after {  /* a row of rising bars in the corner */
    content: ""; position: absolute; right: 46px; bottom: 0; width: 210px; height: 150px; opacity: 0.20;
    background: linear-gradient(#fff, #fff) 0 100% / 30px 35% no-repeat, linear-gradient(#fff, #fff) 45px 100% / 30px 55% no-repeat,
                linear-gradient(#fff, #fff) 90px 100% / 30px 45% no-repeat, linear-gradient(#fff, #fff) 135px 100% / 30px 75% no-repeat,
                linear-gradient(#fff, #fff) 180px 100% / 30px 100% no-repeat;
}
.hero h1 { color: #ffffff; font-size: 2.35rem; font-weight: 800; margin: 0 0 8px 0; padding: 0; letter-spacing: -0.02em; max-width: 820px; }
.hero p { color: #ccfbf1; font-size: 1.03rem; margin: 0; max-width: 760px; line-height: 1.55; }
.hero .tag { display: inline-block; background: rgba(255, 255, 255, 0.16); border: 1px solid rgba(255, 255, 255, 0.25);
             border-radius: 999px; padding: 4px 14px; font-size: 0.74rem; font-weight: 600; margin-bottom: 14px; letter-spacing: 0.08em; }
.hero .stack { margin-top: 16px; font-size: 0.82rem; color: #99f6e4; }
.hero a.code { display: inline-block; margin-top: 16px; padding: 8px 18px; border-radius: 999px; background: #f59e0b;
               color: #042f2e !important; font-weight: 700; font-size: 0.86rem; text-decoration: none !important; }
.hero a.code:hover { background: #fbbf24; }

/* ---------- header band at the top of every other page ---------- */
.report-header {
    background: linear-gradient(120deg, #042f2e 0%, #0f766e 100%); color: #ffffff; padding: 18px 24px; border-radius: 16px;
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;
    box-shadow: 0 8px 22px rgba(15, 118, 110, 0.22); border-left: 6px solid #f59e0b;
}
.report-header .title { font-size: 1.45rem; font-weight: 700; letter-spacing: -0.01em; }
.report-header .subtitle { font-size: 0.9rem; color: #99f6e4; margin-top: 2px; }
.report-header .right { font-size: 0.85rem; text-align: right; color: #ccfbf1; }

/* ---------- feature cards on the home page: the whole card is a link ---------- */
a.feature-link, a.feature-link:hover, a.feature-link:visited { text-decoration: none !important; display: block; }
.feature {
    position: relative; height: 168px; padding: 20px 20px 16px 20px; border-radius: 20px; color: #ffffff; cursor: pointer;
    margin-bottom: 14px; overflow: hidden;
    box-shadow: 0 8px 20px rgba(4, 47, 46, 0.14); transition: transform 0.18s ease, box-shadow 0.18s ease;
}
.feature::before {  /* soft glow in the corner */
    content: ""; position: absolute; right: -40px; top: -40px; width: 140px; height: 140px; border-radius: 50%;
    background: rgba(255, 255, 255, 0.16);
}
.feature:hover { transform: translateY(-7px); box-shadow: 0 18px 36px rgba(4, 47, 46, 0.28); }
.feature .icon { width: 44px; height: 44px; border-radius: 14px; display: flex; align-items: center; justify-content: center;
                 font-size: 1.35rem; margin-bottom: 12px; background: rgba(255, 255, 255, 0.22); }
.feature .name { font-weight: 700; color: #ffffff; font-size: 1.05rem; margin-bottom: 5px; }
.feature .text { color: rgba(255, 255, 255, 0.90); font-size: 0.84rem; line-height: 1.45; }
.feature .arrow { position: absolute; right: 18px; bottom: 12px; font-size: 1.25rem; color: #ffffff; opacity: 0.6;
                  transition: transform 0.18s ease, opacity 0.18s ease; }
.feature:hover .arrow { transform: translateX(6px); opacity: 1; }
.feature.teal   { background: linear-gradient(140deg, #0f766e 0%, #14b8a6 100%); }
.feature.amber  { background: linear-gradient(140deg, #d97706 0%, #f59e0b 60%, #fbbf24 100%); }
.feature.sky    { background: linear-gradient(140deg, #0369a1 0%, #0ea5e9 100%); }
.feature.rose   { background: linear-gradient(140deg, #be123c 0%, #f43f5e 100%); }
.feature.violet { background: linear-gradient(140deg, #5b21b6 0%, #8b5cf6 100%); }
.feature.lime   { background: linear-gradient(140deg, #3f6212 0%, #65a30d 60%, #84cc16 100%); }
.feature.ink    { background: linear-gradient(140deg, #042f2e 0%, #134e4a 60%, #0f766e 100%); }
.feature.coral  { background: linear-gradient(140deg, #c2410c 0%, #f97316 100%); }

/* ---------- finding cards on the home page ---------- */
.finding { background: #ffffff; border: 1px solid #e2ece9; border-left: 5px solid #0d9488; padding: 14px 18px;
           border-radius: 14px; margin-bottom: 12px; box-shadow: 0 2px 8px rgba(4, 47, 46, 0.05); line-height: 1.55; }
.finding .number { font-size: 1.5rem; font-weight: 800; color: #0f766e; letter-spacing: -0.01em; }
.finding .name { font-weight: 700; color: #042f2e; margin: 2px 0 4px 0; }
.finding .text { color: #475569; font-size: 0.9rem; }
.finding.amber { border-left-color: #f59e0b; } .finding.amber .number { color: #b45309; }
.finding.rose  { border-left-color: #e11d48; } .finding.rose .number  { color: #be123c; }
.finding.sky   { border-left-color: #0ea5e9; } .finding.sky .number   { color: #0369a1; }
.finding.violet{ border-left-color: #7c3aed; } .finding.violet .number{ color: #5b21b6; }

/* ---------- chat ---------- */
[data-testid="stChatMessage"] { background: #ffffff; border: 1px solid #e2ece9; border-radius: 16px; box-shadow: 0 2px 8px rgba(4, 47, 46, 0.05); }
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
    figure.update_yaxes(gridcolor="#e2ece9", zeroline=False)
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
