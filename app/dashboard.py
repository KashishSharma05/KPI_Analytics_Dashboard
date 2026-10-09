"""Project website: the story, the dashboard and how it was built.

Run with:  streamlit run app/dashboard.py

Every page reads small files in app/data/ (written by src/export.py and
src/showcase.py), so the site works without a database. The live
"Ask your data" chat needs the PostgreSQL database and a Gemini API key,
so it only appears when both are configured.
"""

import os
import sys

# Allow "from src..." imports for the Ask-your-data page.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from dotenv import load_dotenv

from common import apply_style

load_dotenv()

st.set_page_config(page_title="KPI Analytics & Anomaly Monitoring", page_icon="📊", layout="wide")
apply_style()

pages = {
    "Project": [
        st.Page("views/home.py", title="Home", icon="🏠", default=True),
        st.Page("views/business_case.py", title="Business case", icon="💼"),
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
        st.Page("views/built_ai.py", title="AI assistant", icon="🤖"),
    ],
}
if os.getenv("DATABASE_URL") and os.getenv("GEMINI_API_KEY"):
    pages["How it was built"].append(st.Page("ask_your_data.py", title="Ask your data (live)", icon="💬"))

st.navigation(pages).run()
