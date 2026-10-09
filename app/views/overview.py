"""Page 1: headline KPIs, the trend of one KPI with its anomalies, and monthly growth."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import BLUE, GREY, KPI_LABELS, ORANGE, RED, add_kpis, load, money, month_filter, percent_change, total_kpis

st.title("Business overview")
st.caption("Olist e-commerce marketplace, Brazil. Orders are counted on the day they were placed.")

start, end = month_filter()

daily = load("daily")
daily = daily[daily["date_key"].between(start, end)]

# ---------------------------------------------------------------- KPI cards
# The change shown under each card compares the last month of the chosen
# period with the month before it.
monthly = add_kpis(daily.groupby(daily["date_key"].dt.to_period("M")).sum(numeric_only=True))
latest = monthly.iloc[-1]
previous = monthly.iloc[-2] if len(monthly) > 1 else None
period = total_kpis(daily)


def card(column, label, value_text, kpi, higher_is_better=True):
    change = percent_change(latest[kpi], previous[kpi]) if previous is not None else None
    column.metric(
        label,
        value_text,
        None if change is None else f"{change:+.1f}% last month",
        delta_color="normal" if higher_is_better else "inverse",
    )


c1, c2, c3, c4, c5 = st.columns(5)
card(c1, "Revenue", money(period["revenue"]), "revenue")
card(c2, "Orders", f"{period['orders']:,.0f}", "orders")
card(c3, "Average order value", money(period["aov"]), "aov")
card(c4, "Late delivery rate", f"{period['late_delivery_rate']:.1f}%", "late_delivery_rate", higher_is_better=False)
card(c5, "Average review score", f"{period['avg_review_score']:.2f} / 5", "avg_review_score")

# ------------------------------------------------------- trend with anomalies
st.subheader("Daily trend and anomalies")
kpi = st.selectbox("KPI", list(KPI_LABELS), format_func=KPI_LABELS.get)

trend = add_kpis(daily).set_index("date_key")
# 7-day average: for rates and averages it is recalculated from 7 days of counts.
weekly_sums = daily.set_index("date_key").select_dtypes("number").rolling(7, min_periods=7).sum()
smooth = add_kpis(weekly_sums)[kpi] if kpi not in ("revenue", "orders") else trend[kpi].rolling(7, min_periods=7).mean()

anomalies = load("anomalies")
anomalies = anomalies[(anomalies["kpi"] == kpi) & anomalies["anomaly_date"].between(start, end)]

figure = go.Figure()
figure.add_scatter(x=trend.index, y=trend[kpi], name="Daily", mode="lines", line=dict(color=GREY, width=1))
figure.add_scatter(x=smooth.index, y=smooth, name="7-day average", mode="lines", line=dict(color=BLUE, width=2.5))
for severity, colour in (("medium", ORANGE), ("high", RED)):
    points = anomalies[anomalies["severity"] == severity]
    figure.add_scatter(
        x=points["anomaly_date"], y=points["value"], name=f"Anomaly ({severity})", mode="markers",
        marker=dict(color=colour, size=11, line=dict(color="white", width=1.5)),
        customdata=points[["expected", "deviation_pct"]],
        hovertemplate="%{x|%d %b %Y}<br>value %{y:,.2f}<br>expected %{customdata[0]:,.2f}"
                      "<br>deviation %{customdata[1]:+.1f}%<extra></extra>",
    )

incomplete = trend.index[~trend["is_complete_data"].astype(bool)]
if len(incomplete):
    figure.add_vrect(x0=incomplete.min(), x1=incomplete.max(), fillcolor=GREY, opacity=0.18, line_width=0,
                     annotation_text="incomplete data", annotation_position="top left")

figure.update_layout(height=420, margin=dict(l=10, r=10, t=30, b=10), yaxis_title=KPI_LABELS[kpi],
                     legend=dict(orientation="h", y=1.12), hovermode="x unified")
st.plotly_chart(figure, width="stretch")
st.caption(
    f"{len(anomalies)} anomalies for this KPI in the period "
    f"({(anomalies['severity'] == 'high').sum()} high). Each day is compared with the 28 days before it "
    "using a z-score, an IQR rule and an Isolation Forest. The last days of the data export "
    "(after 22 Aug 2018) are incomplete and are not checked."
)

# ------------------------------------------------------------ monthly growth
st.subheader("Monthly revenue and growth")
monthly_view = monthly.copy()
monthly_view.index = monthly_view.index.to_timestamp()
monthly_view["growth"] = monthly_view["revenue"].pct_change() * 100

figure = go.Figure()
figure.add_bar(x=monthly_view.index, y=monthly_view["revenue"], name="Revenue", marker_color=BLUE)
figure.add_scatter(x=monthly_view.index, y=monthly_view["growth"], name="Month-over-month growth %",
                   mode="lines+markers", line=dict(color=ORANGE, width=2), yaxis="y2")
figure.update_layout(
    height=380, margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=1.12),
    yaxis=dict(title="Revenue (R$)"),
    yaxis2=dict(title="Growth %", overlaying="y", side="right", showgrid=False, zeroline=True),
)
st.plotly_chart(figure, width="stretch")

with st.expander("Monthly numbers"):
    table = monthly_view[["orders", "revenue", "aov", "late_delivery_rate", "avg_review_score", "growth"]].copy()
    table.index = table.index.strftime("%Y-%m")
    table.columns = ["Orders", "Revenue", "AOV", "Late delivery %", "Avg review", "Revenue growth %"]
    st.dataframe(table.round(2), width="stretch")
