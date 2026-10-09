"""How it was built, part 2: the text-to-SQL assistant, its safety checks and its accuracy."""

import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from common import BLUE, GREY, PROJECT_DIR, load_json, result_table

st.title("AI assistant: ask the data in plain English")
st.markdown(
    "The assistant turns a business question into a SQL query, runs it safely and explains the result. "
    "**The LLM never calculates a number**: every figure comes from the database."
)

st.graphviz_chart(
    """
    digraph {
        rankdir=LR; bgcolor="transparent";
        node [shape=box, style="rounded,filled", fillcolor="#1e293b", fontcolor="white", color="#475569", fontname="Helvetica", fontsize=11];
        edge [color="#94a3b8"];
        q  [label="Question\\nin English"];
        r  [label="Retrieve (RAG)\\nKPI rules + example queries\\nfrom a FAISS index"];
        g  [label="LLM writes\\none SELECT"];
        s  [label="Safety check\\nSELECT only, mart only", fillcolor="#b45309"];
        d  [label="Run as a\\nread-only DB user", fillcolor="#b45309"];
        a  [label="LLM words the answer\\nfrom the result rows"];
        q -> r -> g -> s -> d -> a;
        d -> g [label="one repair\\nif the query errors", style=dashed, fontcolor="#94a3b8", fontname="Helvetica", fontsize=9];
    }
    """,
    width="stretch",
)

# -------------------------------------------------------------------- examples
st.subheader("Recorded examples")
st.caption("Real questions put to the assistant, with the SQL it wrote and what it answered.")
examples = load_json("assistant_examples")
chosen = st.selectbox("Question", examples, format_func=lambda example: example["question"])

if chosen["error"]:
    st.warning(f"No query was run. The assistant replied: {chosen['answer']}")
    st.caption("The assistant refuses requests to change data, and says so when a question cannot be answered from the tables.")
else:
    st.success(chosen["answer"].replace("$", "\\$"))  # a bare $ would start a maths formula in Markdown
    left, right = st.columns([3, 2])
    left.markdown("**SQL it wrote**")
    left.code(chosen["sql"], language="sql")
    right.markdown("**Result**")
    right.dataframe(result_table(chosen), width="stretch", hide_index=True)
    st.caption("Retrieved for this question: " + "; ".join(chosen["sources"]))

# -------------------------------------------------------------------- accuracy
st.subheader("Accuracy: measured, with and without RAG")
results = pd.read_csv(os.path.join(PROJECT_DIR, "eval", "text_to_sql_results.csv"))
levels = ["easy", "medium", "hard"]
summary = results.groupby("level")[["with_rag", "without_rag"]].mean().reindex(levels) * 100

left, right = st.columns([2, 3])
with left:
    c1, c2 = st.columns(2)
    c1.metric("With RAG", f"{results['with_rag'].sum()}/{len(results)}", f"{100 * results['with_rag'].mean():.0f}%", delta_color="off")
    c2.metric("Without RAG", f"{results['without_rag'].sum()}/{len(results)}", f"{100 * results['without_rag'].mean():.0f}%", delta_color="off")
    st.markdown(
        """
- 25 test questions, each with a hand-written correct query.
- An answer counts only if its **result rows match** the correct query's rows.
- None of the test questions is among the examples in the knowledge base.
- Without RAG the model sees only table and column names.
"""
    )
with right:
    figure = go.Figure()
    figure.add_bar(x=levels, y=summary["with_rag"], name="With RAG", marker_color=BLUE, text=summary["with_rag"].map("{:.0f}%".format))
    figure.add_bar(x=levels, y=summary["without_rag"], name="Without RAG", marker_color=GREY, text=summary["without_rag"].map("{:.0f}%".format))
    figure.update_layout(height=300, margin=dict(l=10, r=10, t=30, b=10), barmode="group",
                         yaxis=dict(title="Correct answers (%)", range=[0, 110]), legend=dict(orientation="h", y=1.15))
    st.plotly_chart(figure, width="stretch")

st.markdown(
    "**What retrieval fixes.** Without it, the model's mistakes are business-rule mistakes: forgetting the analysis "
    "window, returning a rate as a fraction instead of a percentage, and joining the wrong tables. Retrieval supplies "
    "the KPI definitions and worked examples that prevent most of these; the gain is largest on harder questions."
)

with st.expander("All 25 test questions and results"):
    table = results[["id", "level", "question", "with_rag", "without_rag"]].copy()
    table["with_rag"] = table["with_rag"].map({True: "correct", False: "wrong"})
    table["without_rag"] = table["without_rag"].map({True: "correct", False: "wrong"})
    table.columns = ["ID", "Level", "Question", "With RAG", "Without RAG"]
    st.dataframe(table, width="stretch", hide_index=True)

with st.expander("The questions it got wrong with RAG"):
    for row in results[~results["with_rag"]].itertuples():
        st.markdown(f"**{row.question}**")
        st.code(row.with_rag_sql, language="sql")
    st.write("The usual mistake is a missing business rule: counting orders without the analysis-window filter, "
             "or returning one month's figure where an overall figure was asked. The test set is small, "
             "so each question is worth four points.")

# ---------------------------------------------------------------------- safety
st.subheader("Safety: two independent layers")
left, right = st.columns(2)
with left.container(border=True):
    st.markdown("**1. Code check before anything runs**")
    st.write("The SQL is parsed. Only a single `SELECT` on the `mart` schema is allowed, with a row limit. "
             "Anything that writes, any other schema and risky functions are rejected.")
with right.container(border=True):
    st.markdown("**2. A database user that cannot write**")
    st.write("The query runs as a user that has `SELECT` on `mart` only, inside a read-only transaction "
             "with a 10-second timeout. Even a query that slipped past the code check could not change data.")

tests = pd.DataFrame(load_json("guard_tests"))
passed = (tests["outcome"].str.split(":").str[0] == tests["expected"]).sum()
st.markdown(f"**{passed} of {len(tests)} safety tests pass.** Attacks are blocked and normal queries are allowed:")
tests.columns = ["SQL tried", "Should be", "What happened"]
st.dataframe(tests, width="stretch", hide_index=True, height=320)

st.caption("Model: gemini-3.5-flash-lite, embeddings gemini-embedding-001. "
           "The live chat runs on the project's own database, so on this hosted site it is shown as recorded examples.")
