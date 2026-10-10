"""Project website: the story, the dashboard and how it was built.

Run with:  streamlit run app/dashboard.py

Every page reads small files in app/data/ (written by src/export.py and
src/showcase.py), so the site works without a database server.

The "Ask your data" chat needs a Gemini API key. It runs its queries on
PostgreSQL when DATABASE_URL is set, and otherwise on the DuckDB copy of
the mart schema in app/data/mart.duckdb (which is what the hosted site uses).
"""

import os
import sys

# Allow "from src..." imports for the Ask-your-data page.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from dotenv import load_dotenv

from common import apply_style

load_dotenv()

# On the hosted site the API key comes from Streamlit's secrets, not from a .env file.
if not os.getenv("GEMINI_API_KEY"):
    try:
        os.environ["GEMINI_API_KEY"] = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass  # no secrets configured: the chat page says so

st.set_page_config(page_title="KPI Analytics & Anomaly Monitoring", page_icon="📊", layout="wide")
apply_style()

pages = {
    "Project": [
        st.Page("views/home.py", title="Home", icon="🏠", default=True),
        st.Page("views/business_case.py", title="Business case", icon="💼"),
        st.Page("ask_your_data.py", title="Ask your data", icon="💬"),
    ],
    "Dashboard": [
        st.Page("views/executive.py", title="Executive report", icon="📊"),
        st.Page("views/overview.py", title="Trends & anomalies", icon="📈"),
        st.Page("views/sales.py", title="Sales drill-down", icon="🛒"),
        st.Page("views/growth.py", title="Growth & retention", icon="🌱"),
        st.Page("views/anomalies.py", title="Anomalies & root cause", icon="🚨"),
        st.Page("views/customers.py", title="Delivery & customer voice", icon="🚚"),
    ],
    "How it was built": [
        st.Page("views/built_data.py", title="Data model & SQL", icon="🗄️"),
        st.Page("views/built_ai.py", title="How the AI assistant works", icon="🤖"),
    ],
}
st.navigation(pages).run()
