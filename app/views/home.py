"""Home page: what the project is, the headline numbers and the main findings."""

import os

import pandas as pd
import streamlit as st

from common import GITHUB_URL, PROJECT_DIR, load, money, total_kpis

st.markdown(
    f"""
<div class="hero">
  <div class="tag">KPI ANALYTICS · ANOMALY MONITORING · AI ASSISTANT</div>
  <h1>What happened in the business, why, and what to do next</h1>
  <p>An end-to-end analytics project on 100K real e-commerce orders: a SQL data model and KPI layer,
  anomaly detection with root-cause analysis, this dashboard, and an AI assistant that answers business
  questions in plain English by writing and safely running SQL.</p>
  <div class="stack">Built by Kashish Sharma · PostgreSQL · SQL · Python · Pandas · scikit-learn · Streamlit · Plotly · Google Gemini · FAISS</div>
  <a class="code" href="{GITHUB_URL}" target="_blank">View the code on GitHub →</a>
</div>
""",
    unsafe_allow_html=True,
)

# ------------------------------------------------------------ headline numbers
totals = total_kpis(load("daily"))
anomalies = load("anomalies")
evaluation = pd.read_csv(os.path.join(PROJECT_DIR, "eval", "text_to_sql_results.csv"))

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Orders analysed", f"{totals['orders']:,.0f}")
c2.metric("Revenue", money(totals["revenue"]))
c3.metric("KPIs tracked", "8")
c4.metric("Anomalies detected", len(anomalies), f"{(anomalies['severity'] == 'high').sum()} high severity", delta_color="off")
c5.metric("AI assistant accuracy", f"{100 * evaluation['with_rag'].mean():.0f}%",
          f"{100 * evaluation['without_rag'].mean():.0f}% without RAG", delta_color="off")

st.write("")

# --------------------------------------------------------------------- explore
st.subheader("Explore")
# Each card is one link: clicking anywhere on it opens the page.
cards = [
    ("ask_your_data", "💬", "ink", "Ask your data", "Type a business question. The AI assistant writes the SQL, runs it and explains the result."),
    ("executive", "📊", "teal", "Executive report", "Every headline KPI on one page, with period and state filters."),
    ("anomalies", "🚨", "rose", "Anomalies & root cause", "The unusual days, and which categories, states and payment types drove them."),
    ("business_case", "💼", "amber", "Business case", "The order funnel, what late delivery costs, and what to do about it."),
    ("overview", "📈", "sky", "Trends & anomalies", "Daily KPIs with a 7-day average and the flagged days marked."),
    ("sales", "🛒", "violet", "Sales drill-down", "Revenue by category, customer state and payment type."),
    ("growth", "🌱", "lime", "Growth & retention", "New against returning customers, cohorts and repeat purchases."),
    ("customers", "🚚", "coral", "Delivery & customer voice", "Late delivery against review scores, and complaint themes found by an LLM."),
]
for column, (page, icon, colour, title, description) in zip(st.columns(4) + st.columns(4), cards):
    column.markdown(
        f'''<a class="feature-link" href="{page}" target="_self">
                <div class="feature {colour}"><div class="icon">{icon}</div>
                <div class="name">{title}</div><div class="text">{description}</div><div class="arrow">→</div></div></a>''',
        unsafe_allow_html=True,
    )

# -------------------------------------------------------------------- findings
st.subheader("What the data showed")
findings = [
    ("2.8x", "", "Revenue grew 2.8x in a year",
     "From about R$ 377K a month (Jan-Jun 2017) to R$ 1.07M (Jan-Jun 2018)."),
    ("2.27 vs 4.29 stars", "amber", "Late delivery is the clearest driver of bad reviews",
     "Late orders average 2.27 stars against 4.29 for on-time orders. 62% of late orders get 1-2 stars, "
     "compared with 9% of on-time ones (Mann-Whitney U, p < 0.001)."),
    ("19-26% late", "rose", "A delivery crisis in February-March 2018",
     "For orders placed between 19 Feb and 18 Mar the weekly late rate reached 19-26% (normal: about 5%) "
     "and the average review score fell to 3.5."),
    ("+591%", "sky", "Black Friday 2017 was a broad spike",
     "1,176 orders against an expected 170. Credit-card orders made 81% of the extra revenue and "
     "São Paulo 32%, but the top category only 13%."),
    ("27%", "violet", "The biggest complaint is a wrong or incomplete order",
     "In 2,000 low-score reviews labelled by an LLM: wrong or missing item 27%, not received 21%, late delivery 14%."),
    ("3%", "amber", "Almost nobody buys twice",
     "Only 3% of customers placed a second order, so growth depends on new customers."),
]
for column, group in zip(st.columns(2), (findings[::2], findings[1::2])):
    for number, colour, title, detail in group:
        column.markdown(
            f'''<div class="finding {colour}"><div class="number">{number}</div>
                    <div class="name">{title}</div><div class="text">{detail.replace("$", "&#36;")}</div></div>''',  # a bare $ would start a maths formula
            unsafe_allow_html=True,
        )

st.divider()

# -------------------------------------------------------------------- pipeline
st.subheader("How the data flows")
st.graphviz_chart(
    """
    digraph {
        rankdir=LR; bgcolor="transparent"; nodesep=0.35; ranksep=0.45;
        node [shape=box, style="rounded,filled", fillcolor="#134e4a", fontcolor="white", color="#0f766e", fontname="Helvetica", fontsize=13, margin="0.18,0.12"];
        edge [color="#94a3b8"];
        csv   [label="8 CSV files\\n(Olist, Kaggle)"];
        raw   [label="raw\\nloaded with COPY"];
        clean [label="clean\\nflag, never delete"];
        mart  [label="mart\\nstar schema + KPI views"];
        anom  [label="Anomaly detection\\n+ root cause"];
        llm   [label="LLM review\\nthemes"];
        dash  [label="Dashboard", fillcolor="#0d9488"];
        ask   [label="AI assistant\\nquestion → SQL → answer", fillcolor="#0d9488"];
        csv -> raw -> clean -> mart -> anom -> dash;
        mart -> dash; mart -> ask; clean -> llm -> dash;
    }
    """,
    width="stretch",
)

st.divider()
st.subheader("What was built")
st.markdown(
    """
| Layer | What happens |
|---|---|
| Load and validate | 8 CSV files bulk-loaded into PostgreSQL with `COPY`; 19 data-quality checks |
| Clean | Problems are flagged, not deleted; every rule and its row count is logged |
| Model | Star schema with 2 fact tables and 4 dimensions |
| KPIs | 8 KPIs as SQL views at daily, weekly and monthly grain, cross-checked against Pandas |
| Analysis | Trends, seasonality, cohort retention and a hypothesis test |
| Anomalies | Rolling z-score, IQR and Isolation Forest, with SQL root-cause analysis |
| AI | LLM review classification, and a text-to-SQL assistant with RAG, safety checks and measured accuracy |
"""
)
st.caption(
    "Data: Brazilian E-Commerce Public Dataset by Olist (Kaggle, CC BY-NC-SA 4.0). "
    "Analysis window: January 2017 to August 2018."
)
