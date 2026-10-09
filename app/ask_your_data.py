"""Ask-Your-Data: chat page for the AI assistant.

Run with:  streamlit run app/ask_your_data.py

Type a business question. The page shows the answer in words, a chart
when the result suits one, the result table, and the SQL that was run
(showing the SQL lets the user check how the answer was produced).
"""

import os
import sys

# Allow "from src..." imports when Streamlit runs this file from the app/ folder.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st

from src.ai.text_to_sql import answer_question

EXAMPLE_QUESTIONS = [
    "Which month had the highest revenue?",
    "What are the top 5 product categories by revenue?",
    "Show the late delivery rate for each month of 2018.",
    "Which states have the longest average delivery time?",
    "What do customers complain about most in low-score reviews?",
]

st.set_page_config(page_title="Ask Your Data", page_icon="📊", layout="centered")
st.title("Ask Your Data")
st.caption("Olist e-commerce KPIs, January 2017 to August 2018. Ask in plain English.")


def show_chart(rows):
    """Line chart for a time series, bar chart for categories, nothing otherwise."""
    if len(rows) < 2 or len(rows.columns) < 2:
        return
    first_column = rows.columns[0]
    numeric_columns = [c for c in rows.columns[1:] if pd.api.types.is_numeric_dtype(pd.to_numeric(rows[c], errors="coerce")) and pd.to_numeric(rows[c], errors="coerce").notna().all()]
    if not numeric_columns:
        return

    chart_data = rows[[first_column] + numeric_columns[:2]].copy()
    for column in numeric_columns[:2]:
        chart_data[column] = pd.to_numeric(chart_data[column])

    looks_like_time = any(word in first_column.lower() for word in ("date", "month", "week", "year", "day_key"))
    if looks_like_time:
        st.line_chart(chart_data, x=first_column)
    elif len(rows) <= 30:
        st.bar_chart(chart_data, x=first_column)


def show_result(result):
    if result["error"]:
        st.warning(result["answer"] or result["error"])
        if result["sql"]:
            st.code(result["sql"], language="sql")
        return

    st.write(result["answer"])
    show_chart(result["rows"])
    with st.expander(f"Result table ({len(result['rows'])} rows)"):
        st.dataframe(result["rows"], hide_index=True)
    with st.expander("SQL that was run"):
        st.code(result["sql"], language="sql")
        st.caption("Retrieved for this question: " + "; ".join(result["sources"][:6]))


# The conversation is kept in the session so it stays on screen between questions.
if "history" not in st.session_state:
    st.session_state.history = []

with st.sidebar:
    st.subheader("Try a question")
    for example in EXAMPLE_QUESTIONS:
        if st.button(example, use_container_width=True):
            st.session_state.pending_question = example
    st.divider()
    st.caption(
        "How it works: the question is matched to KPI definitions and example queries, "
        "an LLM writes one SELECT, a safety check and a read-only database user run it, "
        "and the LLM words the answer from the result rows."
    )

for past in st.session_state.history:
    with st.chat_message("user"):
        st.write(past["question"])
    with st.chat_message("assistant"):
        show_result(past)

question = st.chat_input("Ask a question about orders, revenue, delivery or reviews")
question = question or st.session_state.pop("pending_question", None)

if question:
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        with st.spinner("Writing and running the query..."):
            result = answer_question(question)
        show_result(result)
    st.session_state.history.append(result)
