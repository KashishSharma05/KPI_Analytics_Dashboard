"""Growth and retention: where growth comes from, and whether customers come back."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from common import AMBER, GREY, PRIMARY, SKY, chart_layout, load, money, month_filter, report_header

start, end = month_filter()

report_header("Growth & Retention", "Where growth comes from, and whether customers come back",
              f"{start:%b %Y} to {end:%b %Y}")

monthly = load("customer_monthly")
monthly = monthly[monthly["month_start"].between(start, end)]
value = load("customer_value").set_index("orders_placed")

customers = value["customers"].sum()
repeat_customers = value.loc[value.index != "1 order", "customers"].sum()
repeat_revenue = value.loc[value.index != "1 order", "revenue"].sum()
one_time_value = value.loc["1 order", "revenue_per_customer"]
repeat_value = repeat_revenue / repeat_customers

t1, t2, t3, t4, t5 = st.columns(5)
t1.metric("New customers (period)", f"{monthly['new_customers'].sum():,.0f}")
t2.metric("Revenue from new customers", f"{100 * monthly['revenue_new'].sum() / (monthly['revenue_new'].sum() + monthly['revenue_returning'].sum()):.1f}%")
t3.metric("Repeat customers", f"{100 * repeat_customers / customers:.1f}%", f"{repeat_customers:,.0f} of {customers:,.0f}", delta_color="off")
t4.metric("Value of a one-time customer", money(one_time_value))
t5.metric("Value of a repeat customer", money(repeat_value), f"{repeat_value / one_time_value:.1f}x a one-time customer", delta_color="off")
st.caption("The last three tiles cover the whole analysis window; a customer's history cannot be cut to a shorter period.")

# ------------------------------------------------------------------------ row 1
left, right = st.columns([3, 2])

with left.container(border=True):
    st.markdown('<div class="tile-title">Customers by month: new and returning</div>', unsafe_allow_html=True)
    figure = go.Figure()
    figure.add_bar(x=monthly["month_start"], y=monthly["new_customers"], name="New customers", marker_color=PRIMARY)
    figure.add_bar(x=monthly["month_start"], y=monthly["returning_customers"], name="Returning customers", marker_color=AMBER)
    figure.update_layout(barmode="stack")
    st.plotly_chart(chart_layout(figure, 320), width="stretch")
    st.caption("Growth is almost entirely acquisition: the orange band of returning customers is barely visible.")

with right.container(border=True):
    st.markdown('<div class="tile-title">Share of monthly revenue from returning customers (%)</div>', unsafe_allow_html=True)
    share = 100 * monthly["revenue_returning"] / (monthly["revenue_new"] + monthly["revenue_returning"])
    figure = go.Figure()
    figure.add_scatter(x=monthly["month_start"], y=share, mode="lines+markers", line=dict(color=AMBER, width=2.5),
                       fill="tozeroy", name="Returning share")
    figure.update_layout(showlegend=False)
    st.plotly_chart(chart_layout(figure, 320), width="stretch")
    st.caption("It rises slowly as the customer base ages, but stays in the low single digits.")

# ------------------------------------------------------------------------ row 2
left, right = st.columns([3, 2])

with left.container(border=True):
    st.markdown('<div class="tile-title">Which first purchase brings customers back? Repeat rate by first category</div>', unsafe_allow_html=True)
    categories = load("repeat_by_first_category").sort_values("repeat_rate_pct")
    shown = pd.concat([categories.head(5), categories.tail(8)]).drop_duplicates()
    average = 100 * repeat_customers / customers
    figure = px.bar(shown, x="repeat_rate_pct", y="first_category", orientation="h",
                    text=shown["repeat_rate_pct"].map("{:.1f}%".format), color_discrete_sequence=[SKY],
                    labels={"repeat_rate_pct": "", "first_category": ""}, hover_data=["customers", "repeat_customers"])
    figure.add_vline(x=average, line_dash="dash", line_color=GREY, annotation_text=f"average {average:.1f}%")
    st.plotly_chart(chart_layout(figure, 400), width="stretch")
    st.caption("Best 8 and worst 5 categories with at least 500 first-time customers. "
               "Home goods bring people back several times more often than electronics.")

with right.container(border=True):
    st.markdown('<div class="tile-title">How soon does the second order come?</div>', unsafe_allow_html=True)
    gaps = load("second_order_gap")
    gaps["label"] = gaps["gap"].str[3:]
    figure = px.bar(gaps, x="label", y="customers", text="customers", color_discrete_sequence=[PRIMARY],
                    labels={"label": "", "customers": "Repeat customers"})
    st.plotly_chart(chart_layout(figure, 400), width="stretch")
    same_day = gaps.loc[gaps["label"] == "Same day", "customers"].sum()
    st.caption(f"{same_day:,} of {gaps['customers'].sum():,} repeat customers placed their second order on the same day "
               f"as the first. Leaving those out, only {100 * (repeat_customers - same_day) / customers:.1f}% of customers "
               "truly came back on a later day.")

# ------------------------------------------------------------------------ row 3
with st.container(border=True):
    st.markdown('<div class="tile-title">Fastest-growing categories: first half of 2018 against first half of 2017</div>', unsafe_allow_html=True)
    by_category = load("monthly_category_state")
    half_2017 = by_category[by_category["month_start"].between("2017-01-01", "2017-06-30")].groupby("category")["revenue"].sum()
    half_2018 = by_category[by_category["month_start"].between("2018-01-01", "2018-06-30")].groupby("category")["revenue"].sum()
    growth = (half_2018 / half_2017).rename("times").to_frame().join(half_2018.rename("revenue_2018"))
    # only categories that were already a real business in 2017, so a tiny base does not look like huge growth
    growth = growth[half_2017.reindex(growth.index) >= 20000].nlargest(10, "times").reset_index()
    figure = px.bar(growth, x="category", y="times", text=growth["times"].map("{:.1f}x".format),
                    color="revenue_2018", color_continuous_scale="Blues",
                    labels={"times": "Revenue growth (times)", "category": "", "revenue_2018": "H1 2018 revenue"})
    st.plotly_chart(chart_layout(figure, 340), width="stretch")
    st.caption("Categories with at least R$ 20K revenue in the first half of 2017. Darker bars are larger categories today. "
               "This chart always compares the two half-years, whatever period is selected.")

st.page_link("views/customers.py", label="See the monthly cohort retention table", icon="🚚")
