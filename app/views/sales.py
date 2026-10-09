"""Page 2: which categories, states and payment types the revenue comes from."""

import plotly.express as px
import streamlit as st

from common import BLUE, add_kpis, load, money, month_filter, state_filter

st.title("Sales drill-down")

start, end = month_filter()
states = state_filter()


def in_selection(df):
    """Keep rows inside the chosen period and (if any were chosen) the chosen states."""
    df = df[df["month_start"].between(start, end)]
    return df[df["customer_state"].isin(states)] if states else df


by_category_state = in_selection(load("monthly_category_state"))
by_state = in_selection(load("monthly_state"))
by_payment = in_selection(load("monthly_payment_state"))

total_revenue = by_state["revenue"].sum()
c1, c2, c3 = st.columns(3)
c1.metric("Revenue in selection", money(total_revenue))
c2.metric("Orders in selection", f"{by_state['orders'].sum():,.0f}")
c3.metric("Categories sold", by_category_state["category"].nunique())

# ------------------------------------------------------------------ categories
st.subheader("Product categories")
top_n = st.slider("Number of categories to show", 5, 25, 10)

categories = by_category_state.groupby("category", as_index=False)[["revenue", "orders", "items_sold"]].sum()
categories = categories.sort_values("revenue", ascending=False)
categories["share"] = 100 * categories["revenue"] / categories["revenue"].sum()
top = categories.head(top_n)

left, right = st.columns(2)
figure = px.bar(top.iloc[::-1], x="revenue", y="category", orientation="h", text=top.iloc[::-1]["share"].map("{:.1f}%".format),
                color_discrete_sequence=[BLUE], labels={"revenue": "Revenue (R$)", "category": ""})
figure.update_layout(height=max(320, 30 * top_n), margin=dict(l=10, r=10, t=30, b=10), title="Revenue and share of total")
left.plotly_chart(figure, width="stretch")

trend = by_category_state[by_category_state["category"].isin(top["category"].head(5))]
trend = trend.groupby(["month_start", "category"], as_index=False)["revenue"].sum()
figure = px.line(trend, x="month_start", y="revenue", color="category", markers=True,
                 labels={"revenue": "Revenue (R$)", "month_start": "", "category": ""})
figure.update_layout(height=max(320, 30 * top_n), margin=dict(l=10, r=10, t=30, b=10), title="Top 5 categories by month",
                     legend=dict(orientation="h", y=-0.15))
right.plotly_chart(figure, width="stretch")

st.caption(f"The top {top_n} categories bring {top['share'].sum():.0f}% of the revenue in this selection.")

# ---------------------------------------------------------------------- states
st.subheader("Customer states")
state_kpis = add_kpis(by_state.groupby("customer_state").sum(numeric_only=True)).sort_values("revenue", ascending=False)
state_kpis["share"] = 100 * state_kpis["revenue"] / state_kpis["revenue"].sum()

left, right = st.columns(2)
figure = px.bar(state_kpis.head(12).reset_index(), x="customer_state", y="revenue", color_discrete_sequence=[BLUE],
                labels={"revenue": "Revenue (R$)", "customer_state": ""})
figure.update_layout(height=340, margin=dict(l=10, r=10, t=30, b=10), title="Revenue by state (top 12)")
left.plotly_chart(figure, width="stretch")

table = state_kpis[["orders", "revenue", "share", "aov", "late_delivery_rate", "avg_delivery_days", "avg_review_score"]]
table.columns = ["Orders", "Revenue", "Share %", "AOV", "Late delivery %", "Avg delivery days", "Avg review"]
right.dataframe(table.round(2), width="stretch", height=340)

# -------------------------------------------------------------------- payments
st.subheader("Payment types")
payments = by_payment.groupby(["month_start", "main_payment_type"], as_index=False)["orders"].sum()
figure = px.area(payments, x="month_start", y="orders", color="main_payment_type", groupnorm="percent",
                 labels={"orders": "Share of orders (%)", "month_start": "", "main_payment_type": ""})
figure.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10), legend=dict(orientation="h", y=1.12))
st.plotly_chart(figure, width="stretch")
