"""Executive report: the whole business on one page, in a BI-report layout.

Slicers at the top filter every tile. KPI tiles show the selected period and
the change in its last month; the visuals below break the numbers down.
"""

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from common import (AMBER, GREY, PALETTE, PRIMARY, ROSE, SKY, add_kpis, chart_layout, load, money, month_filter,
                    percent_change, report_header, state_filter, total_kpis)

# ----------------------------------------------------------------------- slicers
slicer_left, slicer_right = st.columns([3, 2])
start, end = month_filter(slicer_left)
states = state_filter(slicer_right)


def in_selection(df):
    df = df[df["month_start"].between(start, end)]
    return df[df["customer_state"].isin(states)] if states else df


by_state = in_selection(load("monthly_state"))
by_category = in_selection(load("monthly_category_state"))
by_payment = in_selection(load("monthly_payment_state"))

report_header(
    "Sales & Delivery Performance",
    "Olist e-commerce marketplace, Brazil",
    f"{start:%b %Y} to {end:%b %Y}<br>{', '.join(states) if states else 'All states'}",
)

if by_state.empty:
    st.info("No orders in this selection.")
    st.stop()

# --------------------------------------------------------------------- KPI tiles
monthly = add_kpis(by_state.groupby("month_start").sum(numeric_only=True))
totals = total_kpis(by_state)
latest = monthly.iloc[-1]
previous = monthly.iloc[-2] if len(monthly) > 1 else None


def tile(column, label, value_text, kpi, higher_is_better=True):
    change = percent_change(latest[kpi], previous[kpi]) if previous is not None else None
    column.metric(label, value_text, None if change is None else f"{change:+.1f}% MoM",
                  delta_color="normal" if higher_is_better else "inverse")


t1, t2, t3, t4, t5, t6 = st.columns(6)
tile(t1, "Revenue", money(totals["revenue"]), "revenue")
tile(t2, "Orders", f"{totals['orders']:,.0f}", "orders")
tile(t3, "Avg order value", money(totals["aov"]), "aov")
tile(t4, "Late delivery", f"{totals['late_delivery_rate']:.1f}%", "late_delivery_rate", higher_is_better=False)
tile(t5, "Avg delivery", f"{totals['avg_delivery_days']:.1f} days", "avg_delivery_days", higher_is_better=False)
tile(t6, "Review score", f"{totals['avg_review_score']:.2f}", "avg_review_score")

# ------------------------------------------------------------------------ row 1
left, right = st.columns([2, 1])

with left.container(border=True):
    st.markdown('<div class="tile-title">Revenue and orders by month</div>', unsafe_allow_html=True)
    figure = go.Figure()
    figure.add_bar(x=monthly.index, y=monthly["revenue"], name="Revenue (R$)", marker_color=PRIMARY)
    figure.add_scatter(x=monthly.index, y=monthly["orders"], name="Orders", mode="lines+markers",
                       line=dict(color=AMBER, width=2.5), yaxis="y2")
    figure.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False))
    st.plotly_chart(chart_layout(figure, 300), width="stretch")

with right.container(border=True):
    st.markdown('<div class="tile-title">Orders by payment type</div>', unsafe_allow_html=True)
    payments = by_payment.groupby("main_payment_type", as_index=False)["orders"].sum()
    payments = payments[payments["orders"] >= 10]
    figure = px.pie(payments, names="main_payment_type", values="orders", hole=0.58, color_discrete_sequence=PALETTE)
    figure.update_traces(textinfo="percent", textposition="inside")
    chart_layout(figure, 300).update_layout(legend=dict(orientation="h", y=-0.05, x=0))
    st.plotly_chart(figure, width="stretch")

# ------------------------------------------------------------------------ row 2
left, middle, right = st.columns(3)

with left.container(border=True):
    st.markdown('<div class="tile-title">Top categories by revenue</div>', unsafe_allow_html=True)
    categories = by_category.groupby("category", as_index=False)["revenue"].sum().nlargest(8, "revenue")
    figure = px.bar(categories.iloc[::-1], x="revenue", y="category", orientation="h",
                    text=categories.iloc[::-1]["revenue"].map(money), color_discrete_sequence=[SKY],
                    labels={"revenue": "", "category": ""})
    figure.update_traces(textposition="inside", insidetextanchor="end")
    figure.update_xaxes(showticklabels=False)
    st.plotly_chart(chart_layout(figure, 320), width="stretch")

with middle.container(border=True):
    st.markdown('<div class="tile-title">Revenue by customer state</div>', unsafe_allow_html=True)
    state_revenue = by_state.groupby("customer_state", as_index=False)["revenue"].sum()
    # One box per state, sized and shaded by revenue. No parent box, so every tile is a state.
    figure = go.Figure(
        go.Treemap(
            labels=state_revenue["customer_state"], parents=[""] * len(state_revenue), values=state_revenue["revenue"],
            marker=dict(colors=state_revenue["revenue"], colorscale="Blues", line=dict(color="white", width=2)),
            texttemplate="<b>%{label}</b><br>%{percentRoot:.0%}",
            pathbar=dict(visible=False), root=dict(color="rgba(0,0,0,0)"), tiling=dict(pad=0),
            hovertemplate="%{label}: R$ %{value:,.0f}<extra></extra>",
        )
    )
    st.plotly_chart(chart_layout(figure, 320), width="stretch")

with right.container(border=True):
    st.markdown('<div class="tile-title">Late deliveries and review score</div>', unsafe_allow_html=True)
    figure = go.Figure()
    figure.add_bar(x=monthly.index, y=monthly["late_delivery_rate"], name="Late delivery %", marker_color=ROSE, opacity=0.75)
    figure.add_scatter(x=monthly.index, y=monthly["avg_review_score"], name="Review score", mode="lines+markers",
                       line=dict(color=PRIMARY, width=2.5), yaxis="y2")
    figure.update_layout(yaxis2=dict(overlaying="y", side="right", showgrid=False, range=[3, 5]))
    st.plotly_chart(chart_layout(figure, 320), width="stretch")

# ------------------------------------------------------------------------ row 3
left, right = st.columns([2, 1])

with left.container(border=True):
    st.markdown('<div class="tile-title">State scorecard</div>', unsafe_allow_html=True)
    scorecard = add_kpis(by_state.groupby("customer_state").sum(numeric_only=True)).sort_values("revenue", ascending=False)
    scorecard["share"] = 100 * scorecard["revenue"] / scorecard["revenue"].sum()
    scorecard = scorecard[["orders", "revenue", "share", "aov", "late_delivery_rate", "avg_delivery_days", "avg_review_score"]]
    scorecard.columns = ["Orders", "Revenue", "Share %", "AOV", "Late %", "Delivery days", "Review"]
    styled = (
        scorecard.head(12).style
        .format({"Orders": "{:,.0f}", "Revenue": "R$ {:,.0f}", "Share %": "{:.1f}", "AOV": "R$ {:,.0f}",
                 "Late %": "{:.1f}", "Delivery days": "{:.1f}", "Review": "{:.2f}"})
        # low/high keep the colours pale so the numbers stay readable
        .background_gradient(subset=["Late %", "Delivery days"], cmap="Reds", high=0.6)
        .background_gradient(subset=["Review"], cmap="Greens", high=0.9)
    )
    st.dataframe(styled, width="stretch", height=330)

with right.container(border=True):
    st.markdown('<div class="tile-title">Anomalies in this period</div>', unsafe_allow_html=True)
    anomalies = load("anomalies")
    anomalies = anomalies[anomalies["anomaly_date"].between(start, end)]
    counts = anomalies.groupby(["kpi", "severity"]).size().unstack(fill_value=0).reindex(columns=["high", "medium"], fill_value=0)
    figure = go.Figure()
    figure.add_bar(y=counts.index, x=counts["high"], name="High", orientation="h", marker_color=ROSE)
    figure.add_bar(y=counts.index, x=counts["medium"], name="Medium", orientation="h", marker_color=AMBER)
    figure.update_layout(barmode="stack")
    st.plotly_chart(chart_layout(figure, 250), width="stretch")
    st.caption(f"{len(anomalies)} unusual days, detected for all states together.")
    st.page_link("views/anomalies.py", label="See what drove them", icon="🚨")

st.caption("Use the slicers at the top to change the period or pick states: every tile recalculates. "
           "Revenue counts delivered orders only. Data: Olist public dataset.")
