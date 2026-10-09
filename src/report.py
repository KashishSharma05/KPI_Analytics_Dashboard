"""Executive summary email for the latest complete week.

Run with:  python -m src.report                    (latest complete week; email it if SMTP is set up)
           python -m src.report --no-send          (build the report only)
           python -m src.report --week 2017-11-20  (report for the week starting on that Monday)

Steps:
  1. read the latest complete week's KPIs and the week before it
  2. read the anomalies of that week and their top drivers
  3. ask the LLM for a 5-line summary of exactly those numbers
     (if the LLM call fails, a plain template is used instead)
  4. save the report as reports/latest_report.html
  5. email it, when it is the weekly run or a high-severity anomaly exists

The LLM receives the numbers; it does not calculate any.
"""

import os
import smtplib
import sys
from email.mime.text import MIMEText

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import text

from src.db import get_engine

load_dotenv()

REPORT_PATH = "reports/latest_report.html"

SUMMARY_PROMPT = """You are writing a weekly business summary for the head of an e-commerce company.

Write exactly 5 short bullet points, one per line, each starting with "- ".
- Bullets 1 and 2: the most important KPI movements.
- Bullets 3 and 4: the anomalies and which segments drove them. If there
  were no anomalies, say so in one bullet and use the other for another KPI.
- Bullet 5: the main customer complaint themes, if any are listed.
Use ONLY the numbers given below. Do not invent causes, numbers or advice
that the data does not support. Currency is Brazilian real (R$).

Week starting {week_start}

KPIs this week vs the week before:
{kpi_table}

Anomalies detected this week:
{anomalies}

Top drivers of those anomalies:
{drivers}

Most common complaint themes in low-score reviews this week (from a labelled sample):
{themes}
"""


def table_exists(engine, name):
    with engine.connect() as connection:
        return connection.execute(text("SELECT to_regclass(:n)"), {"n": name}).scalar() is not None


def collect_data(engine, week=None):
    """Everything the report needs, for one week (default: the latest complete week)."""
    weeks = pd.read_sql(
        text("""SELECT * FROM mart.kpi_weekly
                WHERE is_complete_data AND days_in_week = 7
                  AND (CAST(:week AS date) IS NULL OR week_start <= CAST(:week AS date))
                ORDER BY week_start DESC LIMIT 2"""),
        engine, params={"week": week},
    )
    this_week, last_week = weeks.iloc[0], weeks.iloc[1]
    week_start = this_week["week_start"]
    period = {"start": week_start, "end": week_start + pd.Timedelta(days=6)}

    kpis = []
    for label, column in [
        ("Revenue (R$)", "revenue"), ("Orders", "orders"), ("Average order value (R$)", "aov"),
        ("Late delivery rate (%)", "late_delivery_rate"), ("Average review score", "avg_review_score"),
        ("Cancellation rate (%)", "cancellation_rate"),
    ]:
        now, before = float(this_week[column]), float(last_week[column])
        change = 100 * (now - before) / before if before else None
        kpis.append({"KPI": label, "This week": round(now, 2), "Week before": round(before, 2),
                     "Change %": round(change, 1) if change is not None else None})

    anomalies = pd.read_sql(
        text("""SELECT anomaly_date, kpi, value, expected, deviation_pct, direction, severity
                FROM mart.anomalies WHERE anomaly_date BETWEEN :start AND :end
                ORDER BY severity, anomaly_date"""),
        engine, params=period,
    )
    drivers = pd.read_sql(
        text("""SELECT anomaly_date, kpi, dimension, segment, change, contribution_pct
                FROM mart.anomaly_drivers
                WHERE anomaly_date BETWEEN :start AND :end AND driver_rank <= 2
                ORDER BY anomaly_date, kpi, dimension, driver_rank"""),
        engine, params=period,
    )
    themes = pd.DataFrame()
    if table_exists(engine, "mart.review_themes"):
        themes = pd.read_sql(
            text("""SELECT theme, COUNT(*) AS reviews FROM mart.review_themes
                    WHERE order_date BETWEEN :start AND :end AND review_score <= 2
                    GROUP BY theme ORDER BY reviews DESC LIMIT 5"""),
            engine, params=period,
        )
    return {"week_start": week_start, "kpis": pd.DataFrame(kpis), "anomalies": anomalies,
            "drivers": drivers, "themes": themes}


def as_text(df):
    return df.to_string(index=False) if len(df) else "none"


def template_summary(data):
    """Plain summary built without the LLM. Used when the LLM call fails."""
    lines = []
    for row in data["kpis"].head(4).itertuples():
        change = "no change data" if row._4 is None else f"{row._4:+.1f}% vs the week before"
        lines.append(f"- {row.KPI}: {row._2:,.2f} ({change}).")
    high = int((data["anomalies"]["severity"] == "high").sum()) if len(data["anomalies"]) else 0
    lines.append(f"- {len(data['anomalies'])} anomalies detected this week, {high} of them high severity.")
    return "\n".join(lines)


def write_summary(data):
    """LLM summary, with the template as a safety net. Returns (text, source)."""
    try:
        from src.ai.llm import ask, ensure_cache_table

        ensure_cache_table()
        prompt = SUMMARY_PROMPT.format(
            week_start=data["week_start"], kpi_table=as_text(data["kpis"]),
            anomalies=as_text(data["anomalies"]), drivers=as_text(data["drivers"]), themes=as_text(data["themes"]),
        )
        summary = ask(prompt).strip()
        if summary.count("- ") >= 3:  # a usable answer has several bullet points
            return summary, "AI-generated summary"
    except Exception as error:
        print("LLM summary failed, using the template instead:", str(error)[:120])
    return template_summary(data), "Template summary"


def build_html(data, summary, summary_source):
    severity_colour = {"high": "#b42318", "medium": "#b54708"}
    bullets = "".join(f"<li>{line.lstrip('- ').strip()}</li>" for line in summary.splitlines() if line.strip())

    anomalies_html = "<p>No anomalies this week.</p>"
    if len(data["anomalies"]):
        rows = "".join(
            f"<tr><td>{a.anomaly_date}</td><td>{a.kpi}</td><td>{a.value:,.2f}</td><td>{a.expected:,.2f}</td>"
            f"<td>{a.deviation_pct:+.1f}%</td>"
            f"<td style='color:{severity_colour[a.severity]};font-weight:bold'>{a.severity}</td></tr>"
            for a in data["anomalies"].itertuples()
        )
        anomalies_html = (
            "<table><tr><th>Date</th><th>KPI</th><th>Value</th><th>Expected</th><th>Deviation</th><th>Severity</th></tr>"
            + rows + "</table>"
        )

    return f"""<html><body style="font-family:Arial,sans-serif;color:#1d2939;max-width:680px">
<style>table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #d0d5dd;padding:6px 10px;text-align:left}}
th{{background:#f2f4f7}}</style>
<h2>Weekly KPI report - week starting {data['week_start']}</h2>
<h3>Summary</h3><ul>{bullets}</ul><p style="color:#667085;font-size:12px">{summary_source}</p>
<h3>KPIs</h3>{data['kpis'].to_html(index=False, border=0, na_rep='-')}
<h3>Anomalies</h3>{anomalies_html}
</body></html>"""


def send_email(html, subject):
    """Send through Gmail SMTP. Returns True if sent."""
    user, password, recipient = os.getenv("SMTP_USER"), os.getenv("SMTP_APP_PASSWORD"), os.getenv("ALERT_TO")
    if not (user and password and recipient):
        print("Email not sent: SMTP_USER, SMTP_APP_PASSWORD and ALERT_TO are not all set in .env.")
        return False

    message = MIMEText(html, "html")
    message["Subject"], message["From"], message["To"] = subject, user, recipient
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(user, password)
        server.send_message(message)
    print(f"Email sent to {recipient}.")
    return True


def main():
    week = sys.argv[sys.argv.index("--week") + 1] if "--week" in sys.argv else None
    data = collect_data(get_engine(), week)
    summary, summary_source = write_summary(data)
    html = build_html(data, summary, summary_source)

    os.makedirs("reports", exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as report_file:
        report_file.write(html)

    print(f"Week starting {data['week_start']}  |  {summary_source}\n")
    print(summary)
    print(f"\nReport saved to {REPORT_PATH}")

    if "--no-send" not in sys.argv:
        high = int((data["anomalies"]["severity"] == "high").sum()) if len(data["anomalies"]) else 0
        subject = f"Weekly KPI report - {data['week_start']}" + (f" - {high} high-severity anomalies" if high else "")
        send_email(html, subject)


if __name__ == "__main__":
    main()
