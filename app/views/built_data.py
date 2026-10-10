"""How it was built, part 1: data cleaning, the star schema and featured SQL queries."""

import pandas as pd
import streamlit as st

from common import load_json, report_header, result_table

report_header("Data Model & SQL", "Three layers in PostgreSQL, a star schema and the queries behind the KPIs")
st.markdown(
    "The data moves through three layers in PostgreSQL. Each layer has one job, "
    "so a problem can be traced to the step that caused it."
)

c1, c2, c3 = st.columns(3)
with c1.container(border=True):
    st.markdown("**1. raw**")
    st.write("The 8 CSV files exactly as downloaded, bulk-loaded with `COPY`. Primary and foreign keys are "
             "declared, and row counts are checked against the files.")
with c2.container(border=True):
    st.markdown("**2. clean**")
    st.write("Types fixed, categories translated, one review kept per order. Problem rows are flagged, "
             "never deleted, so each KPI can decide what to include.")
with c3.container(border=True):
    st.markdown("**3. mart**")
    st.write("A star schema plus KPI views. The dashboard, the anomaly detector and the AI assistant "
             "all read from here, so they share one definition of every KPI.")

# ------------------------------------------------------------------- cleaning
st.subheader("Cleaning rules and how many rows each one touched")
log = pd.DataFrame(load_json("cleaning_log"))
log.columns = ["Rule", "Rows", "What was done"]
st.dataframe(log, width="stretch", hide_index=True)
st.caption("No order is deleted. The only table that gets smaller is reviews, where repeated reviews of the "
           "same order are reduced to the most recent one.")

# ---------------------------------------------------------------- star schema
st.subheader("Star schema")
left, right = st.columns([3, 2])
with left:
    st.graphviz_chart(
        """
        digraph {
            bgcolor="transparent"; rankdir=LR;
            node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=11, fontcolor="white", color="#0f766e"];
            edge [color="#94a3b8", arrowhead=none];
            fact_orders      [label="fact_orders\\none row per order\\nrevenue, delivery days, is_late, review score", fillcolor="#0d9488"];
            fact_order_items [label="fact_order_items\\none row per item\\nprice, freight, item total", fillcolor="#0d9488"];
            dim_date     [label="dim_date\\nday, week, month, weekday", fillcolor="#134e4a"];
            dim_customer [label="dim_customer\\nunique customer, city, state", fillcolor="#134e4a"];
            dim_product  [label="dim_product\\ncategory", fillcolor="#134e4a"];
            dim_seller   [label="dim_seller\\ncity, state", fillcolor="#134e4a"];
            dim_date -> fact_orders; dim_customer -> fact_orders;
            fact_orders -> fact_order_items;
            fact_order_items -> dim_product; fact_order_items -> dim_seller;
        }
        """,
        width="stretch",
    )
with right:
    st.markdown(
        """
**Why this shape**

- **Facts** hold what is measured: orders and revenue.
- **Dimensions** hold what it is sliced by: date, customer, product, seller.
- Items, payments and reviews each have many rows per order, so they are
  summarised to one row per order *before* joining. Joining them directly
  would multiply rows and double-count revenue.
- Monthly revenue from this model is checked against an independent Pandas
  calculation from the raw files: all 20 months match to the cent.
"""
    )

# ------------------------------------------------------------ featured queries
st.subheader("Featured queries")
st.caption("Each tab shows a business question, the SQL that answers it, and the first rows of the real result.")
queries = load_json("sql_showcase")
for tab, query in zip(st.tabs([q["title"] for q in queries]), queries):
    with tab:
        st.markdown(f"**Question:** {query['question']}")
        st.caption(f"Uses: {query['skills']}")
        left, right = st.columns([3, 2])
        left.code(query["sql"], language="sql")
        right.dataframe(result_table(query), width="stretch", hide_index=True)
        right.caption(f"{query['total_rows']} rows in total.")
