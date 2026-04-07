"""Parlay Builder — cross-sport parlay optimizer."""

import streamlit as st
import pandas as pd
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.models import init_db
from scrapers.odds_api import OddsAPIScraper
from scrapers.espn import ESPNScraper
from models.golf_model import (
    build_profiles_from_data, compute_composite_scores,
    scores_to_probabilities, monte_carlo_tournament,
)
from models.ev_calculator import find_ev_bets
from models.parlay import find_optimal_parlays
from models.kelly import kelly_bet_size
from db.queries import get_bankroll_balance
from utils.odds_math import american_to_decimal, parlay_american_odds

init_db()

st.set_page_config(page_title="Parlay Builder", page_icon="🎲", layout="wide")
st.markdown("# 🎲 Parlay Builder")

odds_api = OddsAPIScraper()
espn = ESPNScraper()

# ── Sidebar ──────────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Parlay Settings")
    max_legs = st.slider("Max legs", 2, 6, 4)
    min_parlay_ev = st.slider("Min parlay EV", 0.0, 1.0, 0.05, 0.05)
    kelly_frac = st.slider("Kelly fraction", 0.1, 0.5, 0.25, 0.05)

tab_auto, tab_manual = st.tabs(["🤖 Auto-Optimizer", "✏️ Manual Builder"])

# ── Tab 1: Auto-Optimizer ───────────────────────────────────────────────────

with tab_auto:
    st.subheader("Optimal Parlays from +EV Pool")

    try:
        odds_by_book = odds_api.get_golf_outright_odds("masters")
        leaderboard = espn.get_golf_leaderboard()

        if odds_by_book and leaderboard:
            rankings = []
            try:
                rankings = espn.get_golf_rankings()
            except Exception:
                pass

            profiles = build_profiles_from_data(leaderboard, rankings)
            mc_results = monte_carlo_tournament(profiles, n_simulations=25000, seed=42)
            predictions = {name: r["win"] for name, r in mc_results.items()}

            ev_bets = find_ev_bets(predictions, odds_by_book, min_ev=0.01)

            if ev_bets:
                st.info(f"Found {len(ev_bets)} +EV singles. Searching parlays...")
                parlays = find_optimal_parlays(
                    ev_bets, max_legs=max_legs, min_parlay_ev=min_parlay_ev
                )

                if parlays:
                    bankroll = get_bankroll_balance() or 1000

                    for i, p in enumerate(parlays[:10]):
                        with st.expander(
                            f"Parlay #{i+1} — {p.leg_count} legs | "
                            f"Odds: +{round(american_to_decimal(0) * 100)}"  # placeholder
                            f" | EV: ${p.ev_per_dollar:.3f}/$ | "
                            f"Prob: {p.combined_model_prob:.2%}"
                        ):
                            legs_data = []
                            for leg in p.legs:
                                legs_data.append({
                                    "Player": leg.player,
                                    "Book": leg.best_book,
                                    "Odds": f"+{leg.best_odds}" if leg.best_odds > 0 else str(leg.best_odds),
                                    "Model Prob": f"{leg.model_prob:.1%}",
                                    "Edge": f"{leg.edge:.1%}",
                                })
                            st.dataframe(pd.DataFrame(legs_data),
                                        use_container_width=True, hide_index=True)

                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Combined Odds",
                                         f"{p.combined_decimal_odds:.1f}x")
                            with col2:
                                st.metric("Joint Probability",
                                         f"{p.combined_model_prob:.3%}")
                            with col3:
                                st.metric("EV per $1", f"${p.ev_per_dollar:.3f}")
                else:
                    st.info("No parlays found meeting your criteria. Try adjusting settings.")
            else:
                st.info("No +EV singles found to build parlays from.")
        else:
            st.warning("Need both odds and leaderboard data to build parlays.")
    except Exception as e:
        st.error(f"Error: {e}")

# ── Tab 2: Manual Builder ───────────────────────────────────────────────────

with tab_manual:
    st.subheader("Build Your Own Parlay")

    if "manual_legs" not in st.session_state:
        st.session_state.manual_legs = []

    col1, col2, col3 = st.columns(3)
    with col1:
        player_name = st.text_input("Player / Team")
    with col2:
        odds_input = st.number_input("American Odds", value=500, step=50)
    with col3:
        prob_input = st.number_input("Your est. probability (%)", value=10.0, step=1.0,
                                      min_value=0.1, max_value=99.0)

    if st.button("Add Leg"):
        st.session_state.manual_legs.append({
            "player": player_name,
            "odds": odds_input,
            "prob": prob_input / 100,
        })
        st.rerun()

    if st.session_state.manual_legs:
        st.divider()
        legs_df = pd.DataFrame(st.session_state.manual_legs)
        legs_df.columns = ["Player", "Odds", "Probability"]
        st.dataframe(legs_df, use_container_width=True, hide_index=True)

        # Calculate parlay
        combined_decimal = 1.0
        combined_prob = 1.0
        for leg in st.session_state.manual_legs:
            combined_decimal *= american_to_decimal(int(leg["odds"]))
            combined_prob *= leg["prob"]

        ev = (combined_prob * (combined_decimal - 1)) - ((1 - combined_prob) * 1.0)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Combined Odds", f"{combined_decimal:.1f}x")
        with col2:
            st.metric("Parlay Prob", f"{combined_prob:.3%}")
        with col3:
            st.metric("EV per $1", f"${ev:.3f}",
                      delta="+ EV" if ev > 0 else "- EV",
                      delta_color="normal" if ev > 0 else "inverse")
        with col4:
            bankroll = get_bankroll_balance() or 1000
            parlay_odds_am = parlay_american_odds([int(l["odds"]) for l in st.session_state.manual_legs])
            kelly = kelly_bet_size(bankroll, combined_prob, parlay_odds_am, fraction=kelly_frac)
            st.metric("Kelly Bet", f"${kelly:.2f}")

        if st.button("Clear All Legs"):
            st.session_state.manual_legs = []
            st.rerun()
