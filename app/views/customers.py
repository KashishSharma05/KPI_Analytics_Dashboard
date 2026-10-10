"""Page 4: delivery performance, what unhappy customers say, and whether customers return."""

import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from common import AMBER, PRIMARY, ROSE, add_kpis, load, month_filter, report_header, state_filter, total_kpis

report_header("Delivery & Customer Voice", "How late delivery moves review scores, and what customers complain about")

start, end = month_filter()
states = state_filter()

by_state = load("monthly_state")
by_state = by_state[by_state["month_start"].between(start, end)]
if states:
    by_state = by_state[by_state["customer_state"].isin(states)]

totals = total_kpis(by_state)
c1, c2, c3 = st.columns(3)
c1.metric("Late delivery rate", f"{totals['late_delivery_rate']:.1f}%")
c2.metric("Average delivery time", f"{totals['avg_delivery_days']:.1f} days")
c3.metric("Average review score", f"{totals['avg_review_score']:.2f} / 5")

# ------------------------------------------------ late deliveries vs review score
st.subheader("Late deliveries and review scores move together")
monthly = add_kpis(by_state.groupby("month_start").sum(numeric_only=True))
figure = go.Figure()
figure.add_bar(x=monthly.index, y=monthly["late_delivery_rate"], name="Late delivery rate (%)", marker_color=AMBER)
figure.add_scatter(x=monthly.index, y=monthly["avg_review_score"], name="Average review score", mode="lines+markers",
                   line=dict(color=PRIMARY, width=2.5), yaxis="y2")
figure.update_layout(
    height=380, margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=1.12),
    yaxis=dict(title="Late delivery rate (%)"),
    yaxis2=dict(title="Average review score", overlaying="y", side="right", showgrid=False, range=[3, 5]),
)
st.plotly_chart(figure, width="stretch")
st.caption(
    "Across all delivered orders, late orders average 2.27 stars and on-time orders 4.29 "
    "(Mann-Whitney U test, p < 0.001; see notebooks/eda.ipynb)."
)

# ------------------------------------------------------------- delivery by state
st.subheader("Delivery time by state")
state_kpis = add_kpis(by_state.groupby("customer_state").sum(numeric_only=True))
state_kpis = state_kpis[state_kpis["delivered_orders"] >= 200].sort_values("avg_delivery_days")
figure = px.bar(state_kpis.reset_index(), x="customer_state", y="avg_delivery_days", color="late_delivery_rate",
                color_continuous_scale="OrRd",
                labels={"avg_delivery_days": "Average delivery days", "customer_state": "", "late_delivery_rate": "Late %"})
figure.update_layout(height=340, margin=dict(l=10, r=10, t=30, b=10))
st.plotly_chart(figure, width="stretch")
st.caption("States with at least 200 delivered orders in the selection. Darker bars have a higher late-delivery rate.")

# --------------------------------------------------------------- complaint themes
st.subheader("What customers complain about")
reviews = load("review_themes")
reviews = reviews[reviews["order_date"].between(start, end)]
if states:
    reviews = reviews[reviews["customer_state"].isin(states)]
low = reviews[reviews["review_score"] <= 2]

left, right = st.columns([3, 2])
if low.empty:
    left.info("No labelled low-score reviews in this selection.")
else:
    themes = low["theme"].value_counts().rename_axis("theme").reset_index(name="reviews")
    themes["share"] = 100 * themes["reviews"] / themes["reviews"].sum()
    figure = px.bar(themes.iloc[::-1], x="reviews", y="theme", orientation="h", text=themes.iloc[::-1]["share"].map("{:.0f}%".format),
                    color_discrete_sequence=[ROSE], labels={"reviews": "Reviews with 1-2 stars", "theme": ""})
    figure.update_layout(height=340, margin=dict(l=10, r=10, t=30, b=10))
    left.plotly_chart(figure, width="stretch")

    theme = right.selectbox("Read reviews about", themes["theme"])
    examples = low[low["theme"] == theme].sort_values("order_date", ascending=False).head(6)
    for summary in examples["english_summary"]:
        right.markdown(f"- {summary}")

st.caption(
    f"{len(low):,} reviews with 1-2 stars in this selection, from a labelled sample of 3,000 reviews. "
    "The comments are in Portuguese; an LLM assigned each one a theme from a fixed list and wrote the English summary. "
    "Because the sample is weighted towards low scores, read these as shares of complaints, not of all orders."
)

# -------------------------------------------------------------------- retention
st.subheader("Do customers come back?")
cohort = load("cohort_retention")
cohort = cohort[cohort["months_since_first"].between(1, 6)]
heatmap = cohort.pivot(index="cohort_month", columns="months_since_first", values="retention_pct")
heatmap.index = heatmap.index.strftime("%Y-%m")
figure = px.imshow(heatmap, text_auto=".2f", aspect="auto", color_continuous_scale="Blues",
                   labels=dict(x="Months since first purchase", y="First purchase month", color="% buying again"))
figure.update_layout(height=520, margin=dict(l=10, r=10, t=30, b=10))
st.plotly_chart(figure, width="stretch")
st.caption("Fewer than 1% of customers buy again in any later month; only 3% ever place a second order. "
           "This chart covers all states and the whole period.")
