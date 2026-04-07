import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Support Streamlit Cloud secrets
try:
    import streamlit as st
    _secrets = st.secrets
except Exception:
    _secrets = {}

DB_PATH = os.getenv("DB_PATH", "data/betting.db")
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "") or _secrets.get("ODDS_API_KEY", "")
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
ESPN_API_BASE = "https://site.api.espn.com/apis/site/v2/sports"

# Cache TTLs in seconds
CACHE_TTL_LIVE = 300        # 5 min for live scores
CACHE_TTL_ODDS = 900        # 15 min for odds
CACHE_TTL_RANKINGS = 3600   # 1 hour for rankings
CACHE_TTL_STATIC = 86400    # 24 hours for historical data
