"""Sports Betting Dashboard — Home Page."""

import streamlit as st
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(__file__))

from db.models import init_db

# Initialize database on startup
init_db()

st.set_page_config(
    page_title="Betting Dashboard",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ───────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #00C853;
        margin-bottom: 0;
    }
    .sub-header {
        font-size: 1.1rem;
        color: #888;
        margin-top: -10px;
        margin-bottom: 30px;
    }
    .sport-card {
        background: #1A1A2E;
        border: 1px solid #333;
        border-radius: 12px;
        padding: 24px;
        text-align: center;
        transition: border-color 0.2s;
    }
    .sport-card:hover {
        border-color: #00C853;
    }
    .sport-card h3 {
        margin-top: 8px;
        color: #FAFAFA;
    }
    .sport-card p {
        color: #888;
        font-size: 0.9rem;
    }
    .kpi-row {
        display: flex;
        gap: 16px;
        margin-bottom: 24px;
    }
    .kpi-box {
        background: #1A1A2E;
        border: 1px solid #333;
        border-radius: 8px;
        padding: 16px 20px;
        flex: 1;
    }
    .kpi-label {
        color: #888;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .kpi-value {
        color: #00C853;
        font-size: 1.8rem;
        font-weight: 700;
    }
    .kpi-value.negative {
        color: #FF5252;
    }
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────────────────────────────

st.markdown('<p class="main-header">Sports Betting Dashboard</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Golf | NFL | Horse Racing — Odds, Models & Strategy</p>', unsafe_allow_html=True)

# ── Quick Stats ──────────────────────────────────────────────────────────────

from db.queries import get_bankroll_balance, get_bet_history

balance = get_bankroll_balance()
bets = get_bet_history()
pending = [b for b in bets if b["result"] == "pending"]
settled = [b for b in bets if b["result"] in ("win", "loss")]
wins = [b for b in settled if b["result"] == "win"]
total_wagered = sum(b["stake"] for b in bets)

col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Bankroll", f"${balance:,.2f}" if balance else "$0.00")
with col2:
    st.metric("Active Bets", len(pending))
with col3:
    win_rate = (len(wins) / len(settled) * 100) if settled else 0
    st.metric("Win Rate", f"{win_rate:.0f}%" if settled else "—")
with col4:
    st.metric("Total Wagered", f"${total_wagered:,.2f}" if total_wagered else "$0.00")

st.divider()

# ── Sport Navigation ─────────────────────────────────────────────────────────

st.subheader("Quick Navigation")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    <div class="sport-card">
        <h3>⛳ Golf</h3>
        <p>Masters leaderboard, odds comparison, model predictions, +EV finder</p>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Open Masters Dashboard", use_container_width=True):
        st.switch_page("pages/1_Masters.py")

with col2:
    st.markdown("""
    <div class="sport-card">
        <h3>🏈 NFL</h3>
        <p>Spreads, moneylines, over/unders, weekly picks</p>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Open NFL Dashboard", use_container_width=True):
        st.switch_page("pages/3_NFL.py")

with col3:
    st.markdown("""
    <div class="sport-card">
        <h3>🏇 Horse Racing</h3>
        <p>Speed figures, morning lines, value overlay</p>
    </div>
    """, unsafe_allow_html=True)
    if st.button("Open Horse Racing", use_container_width=True):
        st.switch_page("pages/4_Horse_Racing.py")

st.divider()

# ── Tools ────────────────────────────────────────────────────────────────────

col1, col2, col3 = st.columns(3)
with col1:
    if st.button("Parlay Builder", use_container_width=True):
        st.switch_page("pages/5_Parlay_Builder.py")
with col2:
    if st.button("Bankroll Manager", use_container_width=True):
        st.switch_page("pages/6_Bankroll.py")
with col3:
    if st.button("Golf Model Tuning", use_container_width=True):
        st.switch_page("pages/2_Golf_Model.py")

# ── Setup Check ──────────────────────────────────────────────────────────────

st.divider()
with st.expander("Setup Status"):
    from config import ODDS_API_KEY
    if ODDS_API_KEY:
        st.success("The Odds API key configured")
    else:
        st.warning(
            "No ODDS_API_KEY set. Add it to `.env` to fetch live odds. "
            "Get a free key at https://the-odds-api.com/"
        )

    if balance == 0:
        st.info(
            "Bankroll is $0. Go to **Bankroll Manager** to set your starting balance."
        )
