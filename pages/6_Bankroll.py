"""Bankroll Manager — deposits, bet tracking, performance analytics."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.models import init_db
from db.queries import (
    get_bankroll_balance, add_bankroll_entry, get_bet_history,
    get_bankroll_history, place_bet, settle_bet,
)

init_db()

st.set_page_config(page_title="Bankroll", page_icon="💵", layout="wide")
st.markdown("# 💵 Bankroll Manager")

# ── Current Balance ──────────────────────────────────────────────────────────

balance = get_bankroll_balance()
st.metric("Current Bankroll", f"${balance:,.2f}")

tab_manage, tab_bets, tab_analytics = st.tabs([
    "💰 Manage", "📋 Bet History", "📊 Analytics"
])

# ── Tab 1: Manage Bankroll ───────────────────────────────────────────────────

with tab_manage:
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Deposit / Withdraw")
        action = st.selectbox("Action", ["Deposit", "Withdrawal"])
        amount = st.number_input("Amount ($)", value=100.0, min_value=0.01, step=10.0)
        note = st.text_input("Note (optional)")

        if st.button("Submit"):
            if action == "Withdrawal" and amount > balance:
                st.error("Insufficient balance")
            else:
                adj = amount if action == "Deposit" else -amount
                new_bal = add_bankroll_entry(action.lower(), adj, note=note)
                st.success(f"{action} of ${amount:.2f} recorded. New balance: ${new_bal:,.2f}")
                st.rerun()

    with col2:
        st.subheader("Log a Bet")
        with st.form("log_bet"):
            player = st.text_input("Player / Team")
            sport = st.selectbox("Sport", ["golf", "nfl", "horse_racing"])
            event = st.text_input("Event", value="The Masters 2026")
            market = st.selectbox("Market", ["outright", "top5", "top10", "top20",
                                              "h2h", "spread", "moneyline", "over_under"])
            book = st.text_input("Sportsbook", value="DraftKings")
            odds = st.number_input("American Odds", value=500, step=50)
            stake = st.number_input("Stake ($)", value=25.0, min_value=0.01, step=5.0)
            model_prob = st.number_input("Model probability (%)", value=0.0,
                                          min_value=0.0, max_value=100.0, step=1.0)

            if st.form_submit_button("Place Bet"):
                if stake > balance:
                    st.error("Insufficient bankroll")
                else:
                    bet_id = place_bet(
                        player, sport, event, market, book, odds, stake,
                        model_prob=model_prob / 100 if model_prob else None,
                    )
                    st.success(f"Bet #{bet_id} placed: {player} {market} @ {odds} for ${stake:.2f}")
                    st.rerun()

# ── Tab 2: Bet History ───────────────────────────────────────────────────────

with tab_bets:
    bets = get_bet_history()

    if bets:
        # Settle pending bets
        pending = [b for b in bets if b["result"] == "pending"]
        if pending:
            st.subheader(f"Pending Bets ({len(pending)})")
            for bet in pending:
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                with col1:
                    st.write(f"**{bet['player_name']}** — {bet['market']} @ "
                            f"{bet['american_odds']} (${bet['stake']:.2f})")
                with col2:
                    if st.button("✅ Win", key=f"win_{bet['id']}"):
                        from utils.odds_math import american_to_decimal
                        payout = bet["stake"] * american_to_decimal(bet["american_odds"])
                        settle_bet(bet["id"], "win", payout)
                        st.rerun()
                with col3:
                    if st.button("❌ Loss", key=f"loss_{bet['id']}"):
                        settle_bet(bet["id"], "loss")
                        st.rerun()
                with col4:
                    if st.button("↩️ Push", key=f"push_{bet['id']}"):
                        settle_bet(bet["id"], "push", bet["stake"])
                        add_bankroll_entry("bet_push", bet["stake"], bet["id"])
                        st.rerun()

            st.divider()

        # Full history
        st.subheader("All Bets")
        df_bets = pd.DataFrame(bets)
        display_cols = ["player_name", "sport", "event_name", "market",
                       "sportsbook", "american_odds", "stake", "result",
                       "payout", "placed_at"]
        available = [c for c in display_cols if c in df_bets.columns]
        st.dataframe(df_bets[available], use_container_width=True, hide_index=True)
    else:
        st.info("No bets logged yet. Use the form above to track your bets.")

# ── Tab 3: Analytics ─────────────────────────────────────────────────────────

with tab_analytics:
    history = get_bankroll_history()
    bets = get_bet_history()

    if history:
        df_hist = pd.DataFrame(history)

        # Balance over time
        st.subheader("Bankroll Over Time")
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df_hist["created_at"],
            y=df_hist["balance_after"],
            mode="lines+markers",
            line=dict(color="#00C853", width=2),
            fill="tozeroy",
            fillcolor="rgba(0, 200, 83, 0.1)",
        ))
        fig.update_layout(
            yaxis_title="Balance ($)",
            template="plotly_dark",
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

    settled = [b for b in bets if b["result"] in ("win", "loss")]
    if settled:
        df_settled = pd.DataFrame(settled)

        col1, col2 = st.columns(2)

        with col1:
            # ROI by sport
            st.subheader("ROI by Sport")
            sport_stats = []
            for sport in df_settled["sport"].unique():
                sport_bets = df_settled[df_settled["sport"] == sport]
                total_staked = sport_bets["stake"].sum()
                total_payout = sport_bets["payout"].fillna(0).sum()
                roi = ((total_payout - total_staked) / total_staked * 100) if total_staked > 0 else 0
                wins = len(sport_bets[sport_bets["result"] == "win"])
                sport_stats.append({
                    "Sport": sport,
                    "Bets": len(sport_bets),
                    "Wins": wins,
                    "Win Rate": f"{wins/len(sport_bets)*100:.0f}%",
                    "Staked": f"${total_staked:.2f}",
                    "Returned": f"${total_payout:.2f}",
                    "ROI": f"{roi:+.1f}%",
                })
            st.dataframe(pd.DataFrame(sport_stats), use_container_width=True, hide_index=True)

        with col2:
            # Results distribution
            st.subheader("Results Distribution")
            result_counts = df_settled["result"].value_counts()
            fig2 = px.pie(
                values=result_counts.values,
                names=result_counts.index,
                color_discrete_map={"win": "#00C853", "loss": "#FF5252", "push": "#FFC107"},
            )
            fig2.update_layout(template="plotly_dark", height=300)
            st.plotly_chart(fig2, use_container_width=True)

        # Drawdown chart
        if len(history) > 2:
            st.subheader("Drawdown")
            balances = [h["balance_after"] for h in history]
            peak = balances[0]
            drawdowns = []
            for b in balances:
                if b > peak:
                    peak = b
                dd = (b - peak) / peak * 100 if peak > 0 else 0
                drawdowns.append(dd)

            fig3 = go.Figure()
            fig3.add_trace(go.Scatter(
                x=df_hist["created_at"] if len(df_hist) == len(drawdowns) else list(range(len(drawdowns))),
                y=drawdowns,
                mode="lines",
                fill="tozeroy",
                line=dict(color="#FF5252"),
                fillcolor="rgba(255, 82, 82, 0.2)",
            ))
            fig3.update_layout(
                yaxis_title="Drawdown (%)",
                template="plotly_dark",
                height=300,
            )
            st.plotly_chart(fig3, use_container_width=True)

            max_dd = min(drawdowns) if drawdowns else 0
            st.metric("Max Drawdown", f"{max_dd:.1f}%")
    elif not history:
        st.info("No bankroll history yet. Start by making a deposit above.")
