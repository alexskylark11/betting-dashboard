"""Sports Betting Dashboard — Home Page."""

import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from db.models import init_db

init_db()

st.set_page_config(
    page_title="Betting Dashboard",
    page_icon="⛳",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
    .main-header { font-size: 2.5rem; font-weight: 700; color: #00C853; }
    .sub-header { font-size: 1.1rem; color: #888; margin-top: -10px; margin-bottom: 30px; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="main-header">Masters Betting Dashboard</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Odds, Models & Strategy</p>', unsafe_allow_html=True)

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
    st.metric("Win Rate", f"{win_rate:.0f}%" if settled else "--")
with col4:
    st.metric("Total Wagered", f"${total_wagered:,.2f}" if total_wagered else "$0.00")

st.divider()

col1, col2 = st.columns(2)
with col1:
    if st.button("Open Masters Dashboard", use_container_width=True, type="primary"):
        st.switch_page("pages/1_Masters.py")
with col2:
    if st.button("Bankroll Manager", use_container_width=True):
        st.switch_page("pages/6_Bankroll.py")

st.divider()
with st.expander("Setup Status"):
    from config import ODDS_API_KEY
    if ODDS_API_KEY:
        st.success("The Odds API key configured")
    else:
        st.warning("No ODDS_API_KEY set. Add it to secrets to fetch live odds.")
    if balance == 0:
        st.info("Bankroll is $0. Go to Bankroll Manager to set your starting balance.")
