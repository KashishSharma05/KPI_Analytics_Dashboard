"""Page 3: the detected anomalies and, for the big ones, what drove them."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from common import BLUE, GREY, KPI_LABELS, ORANGE, RED, add_kpis, load

st.title("Anomalies and root cause")
st.caption(
    "Each day is compared with the 28 days before it. A day is flagged by a rolling z-score (|z| > 3), "
    "an IQR rule, or an Isolation Forest. Severity is high when at least two methods agree or |z| > 4."
)

anomalies = load("anomalies")

c1, c2 = st.columns(2)
chosen_kpis = c1.multiselect("KPI", list(KPI_LABELS), format_func=KPI_LABELS.get, placeholder="All KPIs")
chosen_severity = c2.multiselect("Severity", ["high", "medium"], default=["high"])

shown = anomalies.copy()
if chosen_kpis:
    shown = shown[shown["kpi"].isin(chosen_kpis)]
if chosen_severity:
    shown = shown[shown["severity"].isin(chosen_severity)]

c1, c2, c3 = st.columns(3)
c1.metric("Anomalies shown", len(shown))
c2.metric("Spikes", int((shown["direction"] == "spike").sum()))
c3.metric("Drops", int((shown["direction"] == "drop").sum()))

if shown.empty:
    st.info("No anomalies match these filters.")
    st.stop()

table = shown[["anomaly_date", "kpi", "value", "expected", "deviation_pct", "z_score", "direction",
               "methods_agreeing", "severity"]].copy()
table["anomaly_date"] = table["anomaly_date"].dt.strftime("%Y-%m-%d")
table.columns = ["Date", "KPI", "Value", "Expected", "Deviation %", "z-score", "Direction", "Methods agreeing", "Severity"]
st.dataframe(table, width="stretch", hide_index=True, height=260)

# ---------------------------------------------------------- one anomaly in detail
st.subheader("Look into one anomaly")
options = shown.sort_values("z_score", key=abs, ascending=False)
labels = {
    i: f"{row.anomaly_date:%d %b %Y}  |  {KPI_LABELS[row.kpi]}  |  {row.deviation_pct:+.0f}%  ({row.severity})"
    for i, row in options.iterrows()
}
chosen = options.loc[st.selectbox("Anomaly", list(labels), format_func=labels.get)]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Value", f"{chosen['value']:,.2f}", f"{chosen['deviation_pct']:+.1f}% vs expected")
c2.metric("Expected (28-day average)", f"{chosen['expected']:,.2f}")
c3.metric("z-score", f"{chosen['z_score']:.1f}")
methods = [name for name, flag in (("z-score", chosen["flag_zscore"]), ("IQR", chosen["flag_iqr"]),
                                   ("Isolation Forest", chosen["flag_isolation_forest"])) if flag]
c4.metric("Flagged by", ", ".join(methods))

# The KPI in the weeks around the anomaly.
daily = add_kpis(load("daily")).set_index("date_key")
window = daily.loc[chosen["anomaly_date"] - pd.Timedelta(days=35): chosen["anomaly_date"] + pd.Timedelta(days=14)]
figure = go.Figure()
figure.add_scatter(x=window.index, y=window[chosen["kpi"]], mode="lines+markers", line=dict(color=BLUE), name="Daily")
figure.add_scatter(x=[chosen["anomaly_date"]], y=[chosen["value"]], mode="markers", name="Anomaly",
                   marker=dict(color=RED if chosen["severity"] == "high" else ORANGE, size=14))
figure.add_hline(y=chosen["expected"], line_dash="dash", line_color=GREY, annotation_text="expected")
figure.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10), yaxis_title=KPI_LABELS[chosen["kpi"]],
                     legend=dict(orientation="h", y=1.15))
st.plotly_chart(figure, width="stretch")

# What drove it.
drivers = load("anomaly_drivers")
drivers = drivers[(drivers["anomaly_date"] == chosen["anomaly_date"]) & (drivers["kpi"] == chosen["kpi"])]

if drivers.empty:
    st.info(
        "Driver analysis is available for high-severity revenue and orders anomalies. "
        "Those KPIs add up across segments, so a change can be split between them; a rate or an average cannot."
    )
else:
    st.markdown(
        "**What drove it.** Each segment's value that day is compared with its daily average over the previous "
        "28 days. The label shows the segment's share of the total change."
    )
    titles = {"category": "Product category", "customer_state": "Customer state", "payment_type": "Payment type"}
    for column, (dimension, title) in zip(st.columns(3), titles.items()):
        part = drivers[drivers["dimension"] == dimension].sort_values("change", key=abs)
        figure = px.bar(part, x="change", y="segment", orientation="h", text=part["contribution_pct"].map("{:.0f}%".format),
                        color_discrete_sequence=[BLUE], labels={"change": "Change vs baseline", "segment": ""})
        figure.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10), title=title)
        column.plotly_chart(figure, width="stretch")

    top_state = drivers[(drivers["dimension"] == "customer_state") & (drivers["driver_rank"] == 1)].iloc[0]
    top_category = drivers[(drivers["dimension"] == "category") & (drivers["driver_rank"] == 1)].iloc[0]
    st.caption(
        f"Largest drivers: state {top_state['segment']} ({top_state['contribution_pct']:.0f}% of the change) "
        f"and category {top_category['segment']} ({top_category['contribution_pct']:.0f}%)."
    )
