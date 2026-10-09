"""Find unusual days in the daily KPIs and save them to mart.anomalies.

Run with:  python -m src.detect_anomalies

Three methods are used, and a day is trusted more when methods agree.

1. Rolling z-score
   Compare each day with the 28 days before it.
   z = (value - average of previous 28 days) / standard deviation of previous 28 days
   |z| > 3 means the day is more than 3 standard deviations from normal.
   A rolling window is used (not the all-time average) because the business
   grew a lot: a normal day in 2018 would look "huge" against early 2017.

2. IQR rule
   Take each day's difference from the median of the previous 28 days.
   IQR = Q3 - Q1 of those differences. A day is flagged when its difference
   is more than 3 x IQR outside the Q1..Q3 range (the "extreme outlier" fence).
   Medians and quartiles are not pulled around by a few huge days, so this
   is a second opinion that does not depend on the average.

3. Isolation Forest
   Looks at all KPIs of a day together. It isolates points with random
   splits; unusual days get isolated in fewer splits. It can catch a day
   where no single KPI is extreme but the combination is odd.

Severity: "high" when at least two methods agree or |z| > 4, else "medium".
"""

import pandas as pd
from sklearn.ensemble import IsolationForest
from sqlalchemy import text

from src.db import get_engine

KPIS = ["orders", "revenue", "aov", "late_delivery_rate", "avg_review_score"]

WINDOW_DAYS = 28        # how many previous days form the "normal" baseline
Z_THRESHOLD = 3.0       # z-score flag
Z_HIGH = 4.0            # z-score that alone makes an anomaly high severity
IQR_MULTIPLIER = 3.0    # extreme-outlier fence
IF_CONTAMINATION = 0.02 # Isolation Forest: share of days expected to be unusual


def load_daily_kpis(engine):
    """Daily KPIs, without the incomplete last days of the data export."""
    sql = "SELECT * FROM mart.kpi_daily WHERE is_complete_data ORDER BY date_key"
    df = pd.read_sql(sql, engine, parse_dates=["date_key"]).set_index("date_key")
    return df[KPIS].astype(float)


def score_kpi(values):
    """Return expected value, z-score and IQR flag for one KPI series."""
    # shift(1) so a day is never part of its own baseline
    previous = values.shift(1).rolling(WINDOW_DAYS, min_periods=WINDOW_DAYS)
    expected = previous.mean()
    z_score = (values - expected) / previous.std()

    difference = values - previous.median()
    q1, q3 = difference.quantile(0.25), difference.quantile(0.75)
    iqr = q3 - q1
    iqr_flag = (difference < q1 - IQR_MULTIPLIER * iqr) | (difference > q3 + IQR_MULTIPLIER * iqr)

    return expected, z_score, iqr_flag


def main():
    engine = get_engine()
    daily = load_daily_kpis(engine)

    expected = pd.DataFrame(index=daily.index)
    z_scores = pd.DataFrame(index=daily.index)
    iqr_flags = pd.DataFrame(index=daily.index)
    for kpi in KPIS:
        expected[kpi], z_scores[kpi], iqr_flags[kpi] = score_kpi(daily[kpi])

    # Isolation Forest on the z-scores of all KPIs together.
    # z-scores are used (not raw values) so growth over time is not seen as "unusual".
    usable_days = z_scores.dropna()
    forest = IsolationForest(n_estimators=200, contamination=IF_CONTAMINATION, random_state=42)
    unusual_day = pd.Series(forest.fit_predict(usable_days) == -1, index=usable_days.index)

    rows = []
    for date in usable_days.index:
        # The KPI that is furthest from normal on this day; an Isolation Forest
        # flag for the day is attached to this KPI.
        most_extreme_kpi = z_scores.loc[date].abs().idxmax()

        for kpi in KPIS:
            z = z_scores.loc[date, kpi]
            by_z = abs(z) > Z_THRESHOLD
            by_iqr = bool(iqr_flags.loc[date, kpi])
            by_forest = bool(unusual_day[date]) and kpi == most_extreme_kpi

            methods_agreeing = int(by_z) + int(by_iqr) + int(by_forest)
            if methods_agreeing == 0:
                continue

            value = daily.loc[date, kpi]
            normal = expected.loc[date, kpi]
            rows.append(
                {
                    "anomaly_date": date.date(),
                    "kpi": kpi,
                    "value": round(value, 2),
                    "expected": round(normal, 2),
                    "deviation_pct": round(100 * (value - normal) / normal, 2) if normal else None,
                    "z_score": round(z, 2),
                    "direction": "spike" if value > normal else "drop",
                    "flag_zscore": by_z,
                    "flag_iqr": by_iqr,
                    "flag_isolation_forest": by_forest,
                    "methods_agreeing": methods_agreeing,
                    "severity": "high" if methods_agreeing >= 2 or abs(z) > Z_HIGH else "medium",
                }
            )

    anomalies = pd.DataFrame(rows)

    # DROP ... CASCADE also removes mart.anomaly_drivers, which is built from this table.
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS mart.anomalies CASCADE"))
    anomalies.to_sql("anomalies", engine, schema="mart", index=False)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE mart.anomalies ADD PRIMARY KEY (anomaly_date, kpi)"))

    print(f"Days checked: {len(usable_days)}  ({usable_days.index.min().date()} to {usable_days.index.max().date()})")
    print(f"Anomalies found: {len(anomalies)}\n")
    print(anomalies.groupby(["kpi", "severity"]).size().unstack(fill_value=0).to_string())

    black_friday = anomalies[anomalies["anomaly_date"] == pd.Timestamp("2017-11-24").date()]
    print("\nSanity check - Black Friday (2017-11-24) detected:", "YES" if len(black_friday) else "NO")
    print(black_friday[["kpi", "value", "expected", "deviation_pct", "z_score", "severity"]].to_string(index=False))


if __name__ == "__main__":
    main()
