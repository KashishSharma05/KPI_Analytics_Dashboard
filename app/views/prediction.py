"""Late-delivery prediction: can a late order be spotted when it is placed?"""

import os

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from common import AMBER, DATA_DIR, PRIMARY, ROSE, chart_layout, load_json, report_header

report_header(
    "Late Delivery Prediction",
    "Can an order that will arrive late be spotted at the moment it is placed?",
    "Machine learning · scikit-learn",
)

summary = load_json("ml_summary")
comparison = pd.read_csv(os.path.join(DATA_DIR, "ml_model_comparison.csv"))
importance = pd.read_csv(os.path.join(DATA_DIR, "ml_feature_importance.csv"))
groups = pd.read_csv(os.path.join(DATA_DIR, "ml_risk_groups.csv"))

best = comparison[comparison["model"] == summary["best_model"]].iloc[0]
rule = comparison.iloc[0]
base_rate = summary["test_late_pct"]

st.markdown(
    "Late orders average **2.27 stars** against **4.29** for on-time orders, so knowing in advance which orders are "
    "at risk is worth money: the customer can be warned, or the order sent by a faster route. "
    f"Three models were trained on **{summary['train_orders']:,} orders** placed up to April 2018 and tested on "
    f"**{summary['test_orders']:,} orders** from May to August 2018, using only what is known when the order is placed."
)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Best model", summary["best_model"])
c2.metric("ROC AUC", f"{best['roc_auc']:.2f}", "0.50 = guessing", delta_color="off")
c3.metric(f"Late orders found in the riskiest {summary['flag_share_pct']}%", f"{best['late_orders_found_pct']:.0f}%",
          f"{summary['flag_share_pct']}% expected by chance", delta_color="off")
c4.metric("Flagged orders that were late", f"{best['flagged_that_were_late_pct']:.1f}%",
          f"{base_rate}% across all orders", delta_color="off")

st.info(
    f"**How to read this.** The model is a ranking tool, not a crystal ball. If the business checks the "
    f"{summary['flag_share_pct']}% of orders the model calls riskiest, it finds **{best['late_orders_found_pct']:.0f}%** "
    f"of all late orders, about **{best['late_orders_found_pct'] / summary['flag_share_pct']:.1f} times** what a random "
    f"check would find. Most flagged orders still arrive on time, so the right action is a cheap one, such as an early "
    f"message to the customer."
)

# ------------------------------------------------------------------ comparison
left, right = st.columns([3, 2])
with left.container(border=True):
    st.markdown('<div class="tile-title">Models compared on the test period</div>', unsafe_allow_html=True)
    comparison["model"] = comparison["model"].str.replace("Rule of thumb: state's recent late rate", "Rule of thumb (no model)")
    table = comparison.rename(columns={
        "model": "Model", "roc_auc": "AUC", "average_precision": "Avg precision",
        "late_orders_found_pct": f"Late found in top {summary['flag_share_pct']}% (%)",
        "flagged_that_were_late_pct": "Flagged that were late (%)",
    })
    st.dataframe(table, width="stretch", hide_index=True)
    st.caption(
        f"The first row is not a model: it ranks orders by one rule of thumb. Accuracy is not shown because only "
        f"{base_rate}% of test orders were late, so a model that always says 'on time' would be "
        f"{100 - base_rate:.0f}% accurate and find nothing."
    )

with right.container(border=True):
    st.markdown('<div class="tile-title">Late rate in each risk group (best model)</div>', unsafe_allow_html=True)
    figure = px.bar(groups, x="risk_group", y="late_rate_pct", text="late_rate_pct",
                    color_discrete_sequence=[PRIMARY], labels={"risk_group": "Risk group (1 = riskiest 10%)", "late_rate_pct": "Late (%)"})
    figure.add_hline(y=base_rate, line_dash="dash", line_color=ROSE, annotation_text=f"all orders: {base_rate}%")
    figure.update_xaxes(dtick=1)
    st.plotly_chart(chart_layout(figure, height=290), width="stretch")

# ------------------------------------------------------------------ importance
left, right = st.columns([3, 2])
with left.container(border=True):
    st.markdown('<div class="tile-title">What the model relies on</div>', unsafe_allow_html=True)
    top = importance.head(10).iloc[::-1]
    figure = go.Figure(go.Bar(x=top["importance"], y=top["feature"], orientation="h", marker_color=AMBER))
    figure.update_xaxes(title="Drop in average precision when the column is shuffled")
    st.plotly_chart(chart_layout(figure, height=340), width="stretch")

with right.container(border=True):
    st.markdown('<div class="tile-title">How the test was kept honest</div>', unsafe_allow_html=True)
    st.markdown(
        """
- **Time split, not random.** Train on the past, test on the future, as it would be used.
- **No leakage.** Every column is known at purchase. A seller's or a state's late rate is built only from orders already delivered by then.
- **Unfinished orders left out of training.** An order placed in April but delivered in May had no known result on 1 May.
- **A baseline to beat.** A model only earns its place if it beats a simple rule.
- **Imbalance handled.** Classes are weighted, and the measures used do not reward saying 'never late'.
"""
    )

st.subheader("What this means, and its limits")
st.markdown(
    f"""
- **The promise matters most.** The number of days promised to the customer is by far the strongest signal. This
  suggests lateness has a lot to do with estimates that are too tight for the route, in line with the recommendation
  on the Business case page.
- **Recent conditions matter next.** How deliveries to that state went in the last 30 days adds real information.
- **The model is modest, and that is the honest result.** An AUC of {best['roc_auc']:.2f} is well short of reliable
  prediction. Whether an order is late depends mostly on things this data does not hold: the carrier, weather, strikes
  and stock. The late rate also swings from month to month (1% to 19%), which is hard to learn from 16 months.
- **Next steps:** carrier and distance features, retraining every month, and testing the warning message on a small
  share of flagged orders before rolling it out.
"""
)
st.caption("Models: logistic regression, random forest and gradient boosting (scikit-learn). "
           "Code: sql/09_ml_features.sql and src/ml/train.py.")
