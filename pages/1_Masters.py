"""Masters Tournament Dashboard — leaderboard, odds, model predictions, +EV finder."""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import sys, os
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.models import init_db
from scrapers.espn import ESPNScraper
from scrapers.odds_api import OddsAPIScraper
from models.golf_model import (
    GolferProfile, compute_composite_scores, scores_to_probabilities,
    monte_carlo_tournament, build_profiles_from_data,
)
from models.ev_calculator import find_ev_bets
from models.kelly import kelly_bet_size
from db.queries import get_bankroll_balance
from utils.odds_math import american_to_implied_prob, remove_vig

init_db()

st.set_page_config(page_title="Masters", page_icon="⛳", layout="wide")

# ── Header ───────────────────────────────────────────────────────────────────

col_title, col_status = st.columns([3, 1])
with col_title:
    st.markdown("# ⛳ The Masters")
with col_status:
    st.caption(f"Last refresh: {datetime.now():%H:%M:%S}")

espn = ESPNScraper()
odds_api = OddsAPIScraper()

# ── Sidebar Controls ─────────────────────────────────────────────────────────

with st.sidebar:
    st.header("Settings")
    min_ev = st.slider("Min EV threshold", 0.0, 0.50, 0.02, 0.01,
                        help="Minimum expected value per $1 to flag a bet")
    kelly_fraction = st.slider("Kelly fraction", 0.1, 1.0, 0.25, 0.05,
                                help="Fraction of full Kelly to use (0.25 = quarter)")
    max_bet_pct = st.slider("Max bet % of bankroll", 0.01, 0.10, 0.05, 0.01)
    odds_format = st.radio("Odds format", ["American", "Decimal"])
    run_monte_carlo = st.checkbox("Run Monte Carlo sim", value=True,
                                   help="50K tournament simulations for top-N probs")

    st.divider()
    st.subheader("Auto-Refresh")
    auto_refresh = st.toggle("Enable auto-refresh", value=False,
                              help="Automatically refresh data on interval")
    refresh_interval = st.selectbox("Interval", [30, 60, 120, 300, 600],
                                     format_func=lambda x: f"{x}s" if x < 60 else f"{x//60} min",
                                     index=2)
    if auto_refresh:
        st.caption(f"Refreshing every {refresh_interval}s")

    if st.button("🔄 Refresh Now"):
        st.cache_data.clear()
        st.rerun()

# Auto-refresh via HTML meta tag (doesn't cause Streamlit loop)
if auto_refresh:
    st.markdown(
        f'<meta http-equiv="refresh" content="{refresh_interval}">',
        unsafe_allow_html=True,
    )

# ── Fetch Data ───────────────────────────────────────────────────────────────

tab_leaderboard, tab_odds, tab_ev, tab_model = st.tabs([
    "📋 Leaderboard", "💰 Odds Comparison", "🎯 +EV Finder", "🧠 Model"
])

# ── Tab 1: Leaderboard ──────────────────────────────────────────────────────

with tab_leaderboard:
    try:
        leaderboard = espn.get_golf_leaderboard()
        if leaderboard:
            event_name = leaderboard[0].get("event_name", "The Masters")
            st.subheader(event_name)

            df_lb = pd.DataFrame(leaderboard)
            display_cols = ["position", "name", "total_score", "today", "thru",
                           "round1", "round2", "round3", "round4"]
            available_cols = [c for c in display_cols if c in df_lb.columns]
            st.dataframe(
                df_lb[available_cols],
                use_container_width=True,
                hide_index=True,
                height=600,
            )
            st.caption(f"{len(leaderboard)} players in field")
        else:
            st.info("No active tournament data available from ESPN.")
            leaderboard = []
    except Exception as e:
        st.error(f"Error fetching leaderboard: {e}")
        leaderboard = []

# ── Tab 2: Odds Comparison ──────────────────────────────────────────────────

with tab_odds:
    try:
        odds_by_book = odds_api.get_golf_outright_odds("masters")

        if odds_by_book:
            # Build comparison table: rows = players, cols = sportsbooks
            all_players = sorted(set().union(*(b.keys() for b in odds_by_book.values())))
            books = sorted(odds_by_book.keys())

            rows = []
            for player in all_players:
                row = {"Player": player}
                best_odds = None
                for book in books:
                    odds = odds_by_book[book].get(player)
                    if odds is not None:
                        if odds_format == "Decimal":
                            from utils.odds_math import american_to_decimal
                            row[book] = round(american_to_decimal(odds), 2)
                        else:
                            row[book] = f"+{odds}" if odds > 0 else str(odds)
                        if best_odds is None or odds > best_odds:
                            best_odds = odds
                    else:
                        row[book] = "—"

                # Fair probability (no-vig from consensus)
                all_odds = {b: odds_by_book[b][player]
                           for b in books if player in odds_by_book[b]}
                if all_odds:
                    fair_probs = remove_vig(all_odds)
                    avg_fair = sum(fair_probs.values()) / len(fair_probs)
                    row["Fair Prob"] = f"{avg_fair:.1%}"
                    row["Best Line"] = f"+{best_odds}" if best_odds > 0 else str(best_odds)

                rows.append(row)

            df_odds = pd.DataFrame(rows)
            # Sort by Fair Prob descending
            df_odds["_sort"] = df_odds["Fair Prob"].apply(
                lambda x: float(x.strip("%")) if isinstance(x, str) and "%" in x else 0
            )
            df_odds = df_odds.sort_values("_sort", ascending=False).drop(columns="_sort")

            st.subheader(f"Outright Winner Odds — {len(books)} Sportsbooks")
            st.dataframe(df_odds, use_container_width=True, hide_index=True, height=600)

            if odds_api.remaining_credits is not None:
                st.caption(f"API credits remaining: {odds_api.remaining_credits}")
        else:
            if not os.getenv("ODDS_API_KEY"):
                st.warning(
                    "No ODDS_API_KEY configured. Add your key to `.env` to fetch live odds.\n\n"
                    "Get a free API key at https://the-odds-api.com/"
                )
            else:
                st.info("No Masters odds currently available from The Odds API.")
    except Exception as e:
        st.error(f"Error fetching odds: {e}")

# ── Tab 3: +EV Finder ───────────────────────────────────────────────────────

with tab_ev:
    try:
        odds_by_book = odds_api.get_golf_outright_odds("masters")
        leaderboard = espn.get_golf_leaderboard()

        if odds_by_book and leaderboard:
            # Build profiles and model predictions
            rankings = []
            try:
                rankings = espn.get_golf_rankings()
            except Exception:
                pass

            profiles = build_profiles_from_data(leaderboard, rankings)

            if run_monte_carlo and profiles:
                st.info("Running 50,000 tournament simulations...")
                mc_results = monte_carlo_tournament(profiles, n_simulations=50000)
                predictions = {name: r["win"] for name, r in mc_results.items()}
            else:
                scores = compute_composite_scores(profiles)
                predictions = scores_to_probabilities(scores)

            # Find +EV opportunities
            ev_bets = find_ev_bets(predictions, odds_by_book, market="outright", min_ev=min_ev)

            bankroll = get_bankroll_balance()

            if ev_bets:
                st.subheader(f"🎯 {len(ev_bets)} Positive EV Opportunities")

                rows = []
                for bet in ev_bets:
                    kelly_size = kelly_bet_size(
                        bankroll if bankroll > 0 else 1000,
                        bet.model_prob, bet.best_odds,
                        fraction=kelly_fraction, max_pct=max_bet_pct,
                    )
                    rows.append({
                        "Player": bet.player,
                        "Best Book": bet.best_book,
                        "Best Odds": f"+{bet.best_odds}" if bet.best_odds > 0 else str(bet.best_odds),
                        "Implied Prob": f"{bet.implied_prob:.1%}",
                        "Model Prob": f"{bet.model_prob:.1%}",
                        "Edge": f"{bet.edge:.1%}",
                        "EV / $1": f"${bet.ev_per_dollar:.3f}",
                        "Kelly Bet": f"${kelly_size:.2f}",
                    })

                df_ev = pd.DataFrame(rows)
                st.dataframe(df_ev, use_container_width=True, hide_index=True)

                # Edge visualization
                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=[b.player for b in ev_bets[:20]],
                    y=[b.edge * 100 for b in ev_bets[:20]],
                    marker_color=["#00C853" if b.edge > 0.05 else "#FFC107"
                                  for b in ev_bets[:20]],
                    text=[f"{b.edge:.1%}" for b in ev_bets[:20]],
                    textposition="outside",
                ))
                fig.update_layout(
                    title="Model Edge vs Market (Top 20)",
                    xaxis_title="Player",
                    yaxis_title="Edge (%)",
                    template="plotly_dark",
                    height=400,
                )
                st.plotly_chart(fig, use_container_width=True)

            else:
                st.info(f"No +EV bets found above {min_ev:.0%} threshold. "
                        "Try lowering the minimum EV in the sidebar.")

            # Model vs Market comparison
            if predictions:
                st.subheader("Model vs Market Probabilities")
                comparison = []
                all_books_odds = {}
                for book, players in odds_by_book.items():
                    for player, odds in players.items():
                        if player not in all_books_odds or odds > all_books_odds[player]:
                            all_books_odds[player] = odds

                for name in sorted(predictions.keys(), key=lambda n: predictions[n], reverse=True)[:30]:
                    model_p = predictions[name]
                    market_p = american_to_implied_prob(all_books_odds[name]) if name in all_books_odds else None
                    if market_p:
                        comparison.append({
                            "Player": name,
                            "Model": model_p,
                            "Market": market_p,
                        })

                if comparison:
                    df_cmp = pd.DataFrame(comparison)
                    fig2 = go.Figure()
                    fig2.add_trace(go.Bar(
                        name="Model", x=df_cmp["Player"], y=df_cmp["Model"] * 100,
                        marker_color="#00C853",
                    ))
                    fig2.add_trace(go.Bar(
                        name="Market", x=df_cmp["Player"], y=df_cmp["Market"] * 100,
                        marker_color="#FF5252",
                    ))
                    fig2.update_layout(
                        barmode="group",
                        title="Win Probability: Model vs Market (Top 30)",
                        yaxis_title="Win Prob (%)",
                        template="plotly_dark",
                        height=500,
                    )
                    st.plotly_chart(fig2, use_container_width=True)

        elif not odds_by_book:
            st.warning("No odds data available. Configure ODDS_API_KEY in `.env`.")
        else:
            st.info("Waiting for leaderboard data...")

    except Exception as e:
        st.error(f"Error in EV analysis: {e}")

# ── Tab 4: Model Details ────────────────────────────────────────────────────

with tab_model:
    try:
        leaderboard = espn.get_golf_leaderboard()
        rankings = []
        try:
            rankings = espn.get_golf_rankings()
        except Exception:
            pass

        if leaderboard:
            profiles = build_profiles_from_data(leaderboard, rankings)

            if run_monte_carlo and profiles:
                mc_results = monte_carlo_tournament(profiles, n_simulations=50000, seed=42)

                st.subheader("Monte Carlo Results (50K sims)")
                rows = []
                for name, r in sorted(mc_results.items(), key=lambda x: x[1]["win"], reverse=True)[:40]:
                    rows.append({
                        "Player": name,
                        "Win %": f"{r['win']:.2%}",
                        "Top 5 %": f"{r['top5']:.1%}",
                        "Top 10 %": f"{r['top10']:.1%}",
                        "Top 20 %": f"{r['top20']:.1%}",
                        "Make Cut %": f"{r['make_cut']:.1%}",
                        "Avg Finish": f"{r['avg_finish']:.1f}",
                    })
                df_mc = pd.DataFrame(rows)
                st.dataframe(df_mc, use_container_width=True, hide_index=True, height=500)

                # Probability distribution chart
                top_players = sorted(mc_results.items(), key=lambda x: x[1]["win"], reverse=True)[:15]
                fig = go.Figure()
                for market, color in [("win", "#00C853"), ("top5", "#FFC107"),
                                       ("top10", "#2196F3"), ("top20", "#9C27B0")]:
                    fig.add_trace(go.Bar(
                        name=market.replace("_", " ").title(),
                        x=[p[0] for p in top_players],
                        y=[p[1][market] * 100 for p in top_players],
                        marker_color=color,
                    ))
                fig.update_layout(
                    barmode="group",
                    title="Probability Distribution (Top 15)",
                    yaxis_title="Probability (%)",
                    template="plotly_dark",
                    height=500,
                )
                st.plotly_chart(fig, use_container_width=True)

            # Strokes Gained Radar
            if profiles:
                st.subheader("Strokes Gained Radar")
                selected = st.multiselect(
                    "Select players to compare",
                    [p.name for p in profiles],
                    default=[p.name for p in sorted(profiles, key=lambda x: x.world_ranking)[:3]],
                )
                if selected:
                    categories = ["SG Total", "SG Off Tee", "SG Approach",
                                  "SG Around Green", "SG Putting"]
                    fig_radar = go.Figure()
                    for name in selected:
                        p = next((p for p in profiles if p.name == name), None)
                        if p:
                            values = [p.sg_total, p.sg_off_tee, p.sg_approach,
                                      p.sg_around_green, p.sg_putting]
                            fig_radar.add_trace(go.Scatterpolar(
                                r=values + [values[0]],
                                theta=categories + [categories[0]],
                                name=name,
                            ))
                    fig_radar.update_layout(
                        polar=dict(radialaxis=dict(visible=True)),
                        template="plotly_dark",
                        height=500,
                    )
                    st.plotly_chart(fig_radar, use_container_width=True)

                    st.caption(
                        "Note: Strokes gained data requires seed CSVs or DataGolf API. "
                        "Without data, all SG values default to 0."
                    )
        else:
            st.info("No leaderboard data available.")
    except Exception as e:
        st.error(f"Error in model tab: {e}")
