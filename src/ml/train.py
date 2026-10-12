"""Late-delivery prediction: train, compare and evaluate the models.

Run with:  python -m src.ml.train

Question: at the moment an order is placed, can we tell whether it will
arrive after its estimated delivery date?

How the test is kept honest
  - Time split. The models learn from orders placed up to April 2018 and
    are tested on May to August 2018. A random split would let a model
    learn from orders placed AFTER the ones it is tested on.
  - Training uses only orders that had already been delivered before the
    test period starts, because only their outcome was known by then.
  - Every feature is known at the moment of purchase (sql/09_ml_features.sql).
  - Only about 7% of orders are late, so accuracy is not reported: a model
    that says "never late" would be 93% accurate and useless. The measures
    used instead are ROC AUC, average precision, and how many of the late
    orders are found among the 10% of orders the model calls riskiest.

Results are written to app/data/ for the website.
"""

import json

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.db import get_engine

APP_DATA_DIR = "app/data"
TEST_START = pd.Timestamp("2018-05-01")
RANDOM_STATE = 42
FLAG_SHARE = 0.10  # the share of orders the business could realistically act on

NUMERIC = [
    "promised_days", "purchase_month", "purchase_weekday", "purchase_hour", "same_state",
    "item_count", "seller_count", "items_value", "freight_value", "freight_ratio",
    "total_weight_g", "total_volume_cm3",
    "seller_past_orders", "seller_past_late_rate", "state_recent_orders", "state_recent_late_rate",
]
CATEGORICAL = ["customer_state", "seller_state", "category"]
FEATURES = NUMERIC + CATEGORICAL

FEATURE_LABELS = {
    "promised_days": "Days promised to the customer",
    "purchase_month": "Month of purchase",
    "purchase_weekday": "Day of the week",
    "purchase_hour": "Hour of purchase",
    "same_state": "Seller and customer in the same state",
    "item_count": "Number of items",
    "seller_count": "Number of sellers in the order",
    "items_value": "Value of the items",
    "freight_value": "Freight charge",
    "freight_ratio": "Freight as a share of item value",
    "total_weight_g": "Total weight",
    "total_volume_cm3": "Total volume",
    "seller_past_orders": "Seller: orders delivered so far",
    "seller_past_late_rate": "Seller: share of past orders that were late",
    "state_recent_orders": "State: deliveries in the last 30 days",
    "state_recent_late_rate": "State: late rate in the last 30 days",
    "customer_state": "Customer state",
    "seller_state": "Seller state",
    "category": "Product category",
}


def load_data():
    data = pd.read_sql("SELECT * FROM ml.late_delivery_features", get_engine(),
                       parse_dates=["order_date", "delivered_date"])
    data["is_late"] = data["is_late"].astype(int)
    data["same_state"] = data["same_state"].astype(int)
    for column in NUMERIC:
        data[column] = pd.to_numeric(data[column])

    test = data[data["order_date"] >= TEST_START]
    # An order placed in April but delivered in May had no known outcome on 1 May.
    train = data[(data["order_date"] < TEST_START) & (data["delivered_date"] < TEST_START)]
    return train, test


def prepare(scale):
    """Fill missing numbers with the median, and turn each category into 0/1 columns."""
    numeric_steps = [("fill", SimpleImputer(strategy="median"))]
    if scale:  # logistic regression needs numbers on a similar scale; tree models do not
        numeric_steps.append(("scale", StandardScaler()))
    return ColumnTransformer([
        ("numeric", Pipeline(numeric_steps), NUMERIC),
        ("category", OneHotEncoder(handle_unknown="ignore", min_frequency=50, sparse_output=False), CATEGORICAL),
    ])


def build_models():
    return {
        "Logistic regression": Pipeline([
            ("prepare", prepare(scale=True)),
            ("model", LogisticRegression(class_weight="balanced", max_iter=2000)),
        ]),
        "Random forest": Pipeline([
            ("prepare", prepare(scale=False)),
            ("model", RandomForestClassifier(n_estimators=300, min_samples_leaf=20, class_weight="balanced_subsample",
                                             n_jobs=-1, random_state=RANDOM_STATE)),
        ]),
        "Gradient boosting": Pipeline([
            ("prepare", prepare(scale=False)),
            ("model", HistGradientBoostingClassifier(learning_rate=0.05, max_iter=300, class_weight="balanced",
                                                     random_state=RANDOM_STATE)),
        ]),
    }


def score_model(name, y_true, risk):
    """The three measures for one set of risk scores (higher score = more likely late)."""
    flagged = risk.rank(method="first", ascending=False) <= round(FLAG_SHARE * len(risk))
    late_found = int(y_true[flagged].sum())
    return {
        "model": name,
        "roc_auc": round(roc_auc_score(y_true, risk), 4),
        "average_precision": round(average_precision_score(y_true, risk), 4),
        "late_orders_found_pct": round(100 * late_found / y_true.sum(), 1),   # recall in the flagged 10%
        "flagged_that_were_late_pct": round(100 * late_found / flagged.sum(), 1),  # precision in the flagged 10%
    }


def main():
    train, test = load_data()
    y_train, y_test = train["is_late"], test["is_late"]
    print(f"Train: {len(train):,} orders up to April 2018, {100 * y_train.mean():.1f}% late")
    print(f"Test : {len(test):,} orders May-Aug 2018, {100 * y_test.mean():.1f}% late\n")

    results, risks = [], {}

    # Baseline: no model at all, just one rule of thumb an operations team could use today.
    rule = test["state_recent_late_rate"].fillna(train["state_recent_late_rate"].median())
    results.append(score_model("Rule of thumb: state's recent late rate", y_test, rule))

    models = build_models()
    for name, model in models.items():
        model.fit(train[FEATURES], y_train)
        risks[name] = pd.Series(model.predict_proba(test[FEATURES])[:, 1], index=test.index)
        results.append(score_model(name, y_test, risks[name]))

    comparison = pd.DataFrame(results)
    print(comparison.to_string(index=False))

    best_name = comparison[comparison["model"].isin(models)].sort_values("average_precision").iloc[-1]["model"]
    best_model, best_risk = models[best_name], risks[best_name]
    print(f"\nBest model by average precision: {best_name}")

    # Which features matter: shuffle one column at a time and see how much the score drops.
    importance = permutation_importance(best_model, test[FEATURES], y_test, scoring="average_precision",
                                        n_repeats=5, random_state=RANDOM_STATE, n_jobs=-1)
    importance = pd.DataFrame({
        "feature": [FEATURE_LABELS[f] for f in FEATURES],
        "importance": importance.importances_mean.round(4),
    }).sort_values("importance", ascending=False)
    print("\n" + importance.head(8).to_string(index=False))

    # Ten equal groups from riskiest to safest: a good model puts the late orders in the first groups.
    deciles = pd.DataFrame({"risk": best_risk, "is_late": y_test})
    deciles["risk_group"] = pd.qcut(deciles["risk"].rank(method="first", ascending=False), 10, labels=range(1, 11))
    deciles = deciles.groupby("risk_group", observed=True).agg(orders=("is_late", "size"), late_orders=("is_late", "sum")).reset_index()
    deciles["late_rate_pct"] = (100 * deciles["late_orders"] / deciles["orders"]).round(1)

    comparison.to_csv(f"{APP_DATA_DIR}/ml_model_comparison.csv", index=False)
    importance.to_csv(f"{APP_DATA_DIR}/ml_feature_importance.csv", index=False)
    deciles.to_csv(f"{APP_DATA_DIR}/ml_risk_groups.csv", index=False)
    with open(f"{APP_DATA_DIR}/ml_summary.json", "w", encoding="utf-8") as summary_file:
        json.dump({
            "train_orders": len(train), "train_late_pct": round(100 * y_train.mean(), 1),
            "test_orders": len(test), "test_late_pct": round(100 * y_test.mean(), 1),
            "test_late_orders": int(y_test.sum()),
            "best_model": best_name, "flag_share_pct": int(100 * FLAG_SHARE), "features": len(FEATURES),
        }, summary_file, indent=1)
    print(f"\nWrote ml_model_comparison.csv, ml_feature_importance.csv, ml_risk_groups.csv, ml_summary.json to {APP_DATA_DIR}/")


if __name__ == "__main__":
    main()
