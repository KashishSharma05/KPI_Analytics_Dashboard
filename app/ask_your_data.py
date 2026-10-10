"""Ask-Your-Data: chat page for the AI assistant (a page of app/dashboard.py).

Type a business question. The page shows the answer in words, a check
that the numbers in the answer really are in the query result, a chart
when the result suits one, the result table, and the SQL that was run
(showing the SQL lets the user check how the answer was produced).
"""

import os
import re
import sys

# Allow "from src..." imports when Streamlit runs this file from the app/ folder.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import streamlit as st

from common import report_header

EXAMPLE_QUESTIONS = [
    "Which month had the highest revenue?",
    "What are the top 5 product categories by revenue?",
    "Show the late delivery rate for each month of 2018.",
    "Which states have the longest average delivery time?",
    "What do customers complain about most in low-score reviews?",
    "Which payment type brings in the most revenue?",
]

report_header(
    "Ask your data",
    "Ask a business question in plain English. The assistant writes the SQL, runs it and explains the result.",
    "Olist e-commerce · Jan 2017 to Aug 2018",
)

if not os.getenv("GEMINI_API_KEY"):
    st.warning("The AI assistant is not configured on this copy of the site (no API key). "
               "The page **How the AI assistant works** shows recorded examples.")
    st.stop()

try:
    from src.ai.text_to_sql import answer_question
except Exception as error:  # a package or data file the assistant needs is missing
    st.warning(f"The AI assistant could not start: {error}")
    st.stop()


def check_numbers(answer, rows):
    """How many of the numbers in the answer can be found in the result rows."""
    numbers = re.findall(r"\d+(?:\.\d+)?", answer.replace(",", ""))
    numbers = [n for n in numbers if len(n) > 1 or "." in n]  # single digits are too common to mean anything
    evidence = rows.to_csv(index=False)
    found = 0
    for number in numbers:
        value = float(number)
        variants = {number, f"{value:.0f}", f"{value:.1f}", f"{value:.2f}"}
        found += any(variant in evidence for variant in variants)
    return found, len(numbers)


def show_chart(rows):
    """Line chart for a time series, bar chart for categories, nothing otherwise."""
    if len(rows) < 2 or len(rows.columns) < 2:
        return
    first_column = rows.columns[0]
    as_numbers = {column: pd.to_numeric(rows[column], errors="coerce") for column in rows.columns[1:]}
    numeric_columns = [column for column, values in as_numbers.items() if values.notna().all()]
    if not numeric_columns:
        return

    chart_data = rows[[first_column]].copy()
    for column in numeric_columns[:2]:
        chart_data[column] = as_numbers[column]

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

    st.write(result["answer"].replace("$", "\\$"))  # a bare $ would start a maths formula in Markdown
    found, total = check_numbers(result["answer"], result["rows"])
    if total and found == total:
        st.caption(f"✅ All {total} numbers in this answer were found in the query result.")
    elif total:
        st.caption(f"⚠️ {found} of {total} numbers in this answer were found in the query result. Check the table below.")

    show_chart(result["rows"])
    with st.expander(f"Result table ({len(result['rows'])} rows)"):
        st.dataframe(result["rows"], hide_index=True)
    with st.expander("SQL that was run"):
        st.code(result["sql"], language="sql")
        st.caption("Retrieved for this question: " + "; ".join(result["sources"][:6]))


# The conversation is kept in the session so it stays on screen between questions.
if "history" not in st.session_state:
    st.session_state.history = []

st.markdown("**Try one of these**")
columns = st.columns(3)
for position, example in enumerate(EXAMPLE_QUESTIONS):
    if columns[position % 3].button(example, width="stretch", key=f"example_{position}"):
        st.session_state.pending_question = example

st.caption(
    "How it works: the question is matched to KPI definitions and example queries, an LLM writes one SELECT, "
    "a safety check and a read-only database run it, and the LLM words the answer from the result rows. "
    "Every number comes from the query, never from the model."
)

for past in st.session_state.history:
    with st.chat_message("user"):
        st.write(past["question"])
    with st.chat_message("assistant"):
        show_result(past)

question = st.chat_input("Ask a question about orders, revenue, delivery, customers or reviews")
question = question or st.session_state.pop("pending_question", None)

if question:
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        try:
            with st.spinner("Writing and running the query..."):
                result = answer_question(question)
        except Exception as error:  # usually the free API quota, or the model being busy
            st.warning(f"The assistant could not answer just now: {str(error).splitlines()[0][:200]}")
            st.stop()
        show_result(result)
    st.session_state.history.append(result)

if st.session_state.history and st.button("Clear the conversation"):
    st.session_state.history = []
    st.rerun()
