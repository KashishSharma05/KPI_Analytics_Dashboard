"""Business case: the problem, the customer journey, what to do about it and what it is worth."""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import PRIMARY, chart_layout, load, money, report_header

report_header("Business Case", "From the numbers to what the business should do next", "Olist marketplace, Jan 2017 to Aug 2018")

# ------------------------------------------------------------------ the problem
left, right = st.columns([3, 2])
with left:
    st.subheader("The business problem")
    st.markdown(
        """
Olist grew quickly: monthly revenue went up 2.8x in a year. For a marketplace growing that fast,
three questions decide whether the growth is **healthy**:

- Are orders reaching customers on time, and what happens to satisfaction when they do not?
- When a KPI suddenly moves, how quickly is it noticed, and can anyone say why?
- Is growth coming from customers who come back, or only from finding new ones?

This project answers those three questions from the order data, and turns the answers into
actions with an owner and a way to measure each one.
"""
    )
with right:
    st.subheader("Who needs what")
    st.dataframe(
        pd.DataFrame(
            [
                ("Head of Operations", "Delivery times, late orders, problem regions"),
                ("Customer Experience", "Review scores and what customers complain about"),
                ("Marketing / Growth", "New vs returning customers, which products retain"),
                ("Management", "One page of KPIs, alerts when something is unusual"),
            ],
            columns=["Stakeholder", "What they need to see"],
        ),
        hide_index=True, width="stretch",
    )

# ---------------------------------------------------------------------- funnel
st.subheader("The customer journey: where orders are lost")
funnel = load("funnel_monthly").drop(columns="month_start").sum()
stages = ["Order placed", "Payment approved", "Shipped", "Delivered", "Delivered on time", "On time and rated 4-5 stars"]
counts = funnel[["placed", "approved", "shipped", "delivered", "delivered_on_time", "on_time_and_happy"]].tolist()

left, right = st.columns([3, 2])
with left.container(border=True):
    figure = go.Figure(go.Funnel(y=stages, x=counts, textinfo="value+percent initial", marker=dict(color=PRIMARY)))
    st.plotly_chart(chart_layout(figure, 360), width="stretch")
with right:
    lost_delivery = counts[0] - counts[3]
    lost_late = counts[3] - counts[4]
    lost_unhappy = counts[4] - counts[5]
    st.markdown(
        f"""
**How to read it**

- **{100 * counts[3] / counts[0]:.1f}%** of orders are delivered. Getting the order out of the door is not the problem.
- **{lost_late:,} orders** ({100 * lost_late / counts[3]:.1f}% of delivered) were not delivered by the promised date.
- The biggest drop is the last one: **{lost_unhappy:,} orders** arrive on time and still do not earn 4-5 stars
  (this includes orders that were never reviewed).
- Only **{100 * counts[5] / counts[0]:.0f}%** of orders end as an on-time delivery with a happy review.

So the two places to work on are **delivery promises** and **what is in the box**.
"""
    )

# ------------------------------------------------------------- recommendations
st.subheader("Recommendations")
st.caption("Each one follows from a finding in the data, has an owner, and has a KPI on the dashboard to judge it by.")
recommendations = pd.DataFrame(
    [
        ("Late orders average 2.27 stars; on-time orders 4.29",
         "Set delivery estimates by region from actual delivery times, and tell customers early when an order will be late",
         "Operations", "Late delivery rate; review score of late orders"),
        ("The biggest complaint in 1-2 star reviews is a wrong or incomplete order (27%), ahead of late delivery (14%)",
         "Add a packing check for multi-item orders, and review the sellers with the most wrong-item complaints",
         "Seller management", "Share of 'wrong or missing item' complaints"),
        ("Customers in PA, MA and CE wait over 20 days and have late rates above 11%; São Paulo waits under 9 days",
         "Test a regional carrier or a stocking point for the north and north-east before spending on marketing there",
         "Operations", "Delivery days and late rate by state"),
        ("Late deliveries rose to 19-26% for orders placed 19 Feb to 18 Mar 2018, building up over four weeks; a daily spike check does not catch a slow rise like this",
         "Send the weekly anomaly report to operations, and add a weekly check that catches slow build-ups, not only sudden jumps",
         "Analytics", "Days from the start of a problem to the first alert"),
        ("Only 3% of customers buy again, but a repeat customer is worth 1.9x a one-time customer",
         "Send a follow-up offer after the first delivery, starting with home categories where repeat rates are highest",
         "Marketing / Growth", "Repeat rate; revenue from returning customers"),
        ("7 of 74 categories bring half of revenue; three states bring 63%",
         "Protect stock and seller quality in the top categories first; treat the long tail as a test bed",
         "Category management", "Revenue share and review score of top categories"),
    ],
    columns=["Finding", "Recommendation", "Owner", "How to measure it"],
)
# A Markdown table wraps long text, so every recommendation can be read in full.
header = "| " + " | ".join(recommendations.columns) + " |\n|" + "---|" * len(recommendations.columns)
rows = "\n".join("| " + " | ".join(row) + " |" for row in recommendations.itertuples(index=False))
st.markdown(header + "\n" + rows)

# --------------------------------------------------------------------- sizing
st.subheader("What is at stake")
inputs = load("impact_inputs").iloc[0]
value = load("customer_value").set_index("orders_placed")

late_rate = inputs["late_low_reviews"] / inputs["late_reviewed"]
on_time_rate = inputs["on_time_low_reviews"] / inputs["on_time_reviewed"]
avoidable_reviews = inputs["late_reviewed"] * (late_rate - on_time_rate)
all_low_reviews = inputs["late_low_reviews"] + inputs["on_time_low_reviews"]

customers = value["customers"].sum()
repeat_customers = value.loc[value.index != "1 order", "customers"].sum()
repeat_value = value.loc[value.index != "1 order", "revenue"].sum() / repeat_customers
extra_per_repeat = repeat_value - value.loc["1 order", "revenue_per_customer"]
one_point = customers * 0.01 * extra_per_repeat

c1, c2, c3 = st.columns(3)
with c1.container(border=True):
    st.metric("Bad reviews tied to late delivery", f"{avoidable_reviews:,.0f}")
    st.write(
        f"Late orders get 1-2 stars {100 * late_rate:.0f}% of the time, on-time orders {100 * on_time_rate:.0f}%. "
        f"If late orders had been rated like on-time ones, there would have been about {avoidable_reviews:,.0f} fewer "
        f"bad reviews: {100 * avoidable_reviews / all_low_reviews:.0f}% of all 1-2 star reviews."
    )
with c2.container(border=True):
    st.metric("Value of one more point of repeat rate", money(one_point))
    st.write(
        f"A repeat customer spends about {money(extra_per_repeat)} more than a one-time customer. "
        f"Moving the repeat rate from {100 * repeat_customers / customers:.1f}% up by one point would mean about "
        f"{customers * 0.01:,.0f} more repeat customers over this period."
    )
with c3.container(border=True):
    st.metric("Orders canceled or unavailable", f"{inputs['canceled_orders']:,.0f}")
    st.write(
        f"{money(inputs['canceled_order_value'])} of order value was canceled after items had been chosen. "
        "Most of the other canceled orders were marked unavailable before any item was recorded, which may point "
        "to stock information being out of date."
    )
st.caption(
    "These are sizes of the opportunity, not forecasts. They come from simple arithmetic on the order data and assume "
    "the pattern seen in the data would hold; each recommendation should be tested on a small scale before it is rolled out."
)

# ------------------------------------------------------------------ next steps
st.subheader("Suggested order of work")
st.markdown(
    """
| Priority | Action | Why first |
|---|---|---|
| 1 | Regional delivery estimates and late-order notices | Largest link to bad reviews; needs no new suppliers |
| 2 | Packing check for multi-item orders | Largest complaint theme; a process change, not a spend |
| 3 | Weekly anomaly report to operations | Already built; cost is one email |
| 4 | Follow-up offer after first delivery | Needs a small test to prove the uplift before scaling |
| 5 | North and north-east logistics test | Highest effort; run after the cheaper fixes show results |
"""
)
