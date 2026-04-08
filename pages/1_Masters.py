"""Masters Tournament Dashboard — leaderboard, odds, model, bet slip, parlay builder."""

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
from models.parlay import find_optimal_parlays
from db.queries import (
    get_bankroll_balance, place_bet, settle_bet, get_bet_history,
    add_bankroll_entry,
)
from utils.odds_math import (
    american_to_implied_prob, american_to_decimal, remove_vig,
    parlay_decimal_odds, parlay_american_odds, ev_from_american,
)

init_db()

st.set_page_config(page_title="Masters", page_icon="⛳", layout="wide")

# ── Bet Card CSS ─────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .bet-card {
        background: #1A1A2E;
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 12px;
        border-left: 4px solid #555;
    }
    .bet-card.positive { border-left-color: #00C853; }
    .bet-card.negative { border-left-color: #FF5252; }
    .bet-card.parlay { border-left-color: #FFD700; }
    .bet-card.pending { border-left-color: #2196F3; }
    .bet-card .player { font-size: 1.2rem; font-weight: 700; color: #FAFAFA; }
    .bet-card .detail { color: #888; font-size: 0.85rem; margin-top: 4px; }
    .bet-card .payout { font-size: 1.4rem; font-weight: 700; color: #00C853; margin-top: 8px; }
    .bet-card .profit { color: #00C853; font-size: 0.9rem; }
    .bet-card .stake-info { color: #aaa; font-size: 0.85rem; }
    .bet-card .ev-badge {
        display: inline-block;
        background: #00C853;
        color: #000;
        font-size: 0.75rem;
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 4px;
        margin-left: 8px;
    }
    .bet-card .ev-badge.neg { background: #FF5252; color: #fff; }
    .parlay-leg {
        background: #222244;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 6px 0;
    }
    .parlay-leg .leg-player { font-weight: 600; color: #FAFAFA; }
    .parlay-leg .leg-odds { color: #00C853; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

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
    auto_refresh = st.toggle("Enable auto-refresh", value=False)
    refresh_interval = st.selectbox("Interval", [30, 60, 120, 300, 600],
                                     format_func=lambda x: f"{x}s" if x < 60 else f"{x//60} min",
                                     index=2)
    if auto_refresh:
        st.caption(f"Refreshing every {refresh_interval}s")

    if st.button("Refresh Now"):
        st.cache_data.clear()
        st.rerun()

if auto_refresh:
    st.markdown(
        f'<meta http-equiv="refresh" content="{refresh_interval}">',
        unsafe_allow_html=True,
    )

# ── Preload shared data ─────────────────────────────────────────────────────

@st.cache_data(ttl=300)
def load_leaderboard():
    return espn.get_golf_leaderboard()

@st.cache_data(ttl=900)
def load_odds():
    return odds_api.get_golf_outright_odds("masters")

@st.cache_data(ttl=3600)
def load_rankings():
    try:
        return espn.get_golf_rankings()
    except Exception:
        return []

leaderboard = load_leaderboard()
odds_by_book = load_odds()
rankings = load_rankings()
bankroll = get_bankroll_balance() or 1000

# Build player odds lookup: {player: best_odds} and {player: {book: odds}}
best_odds_map = {}
player_book_odds = {}
if odds_by_book:
    for book, players in odds_by_book.items():
        for player, odds in players.items():
            if player not in player_book_odds:
                player_book_odds[player] = {}
            player_book_odds[player][book] = odds
            if player not in best_odds_map or odds > best_odds_map[player]:
                best_odds_map[player] = odds

books = sorted(odds_by_book.keys()) if odds_by_book else []

# ── Tabs ─────────────────────────────────────────────────────────────────────

tab_leaderboard, tab_odds, tab_ev, tab_model, tab_betslip, tab_parlay = st.tabs([
    "Leaderboard", "Odds Comparison", "+EV Finder", "Model",
    "Bet Slip", "Parlay Builder"
])

# ── Tab 1: Leaderboard ──────────────────────────────────────────────────────

with tab_leaderboard:
    try:
        if leaderboard:
            event_name = leaderboard[0].get("event_name", "The Masters")
            st.subheader(event_name)
            df_lb = pd.DataFrame(leaderboard)
            display_cols = ["position", "name", "total_score", "today", "thru",
                           "round1", "round2", "round3", "round4"]
            available_cols = [c for c in display_cols if c in df_lb.columns]
            st.dataframe(df_lb[available_cols], use_container_width=True,
                        hide_index=True, height=600)
            st.caption(f"{len(leaderboard)} players in field")
        else:
            st.info("No active tournament data available from ESPN.")
    except Exception as e:
        st.error(f"Error fetching leaderboard: {e}")

# ── Tab 2: Odds Comparison ──────────────────────────────────────────────────

with tab_odds:
    try:
        if odds_by_book:
            all_players = sorted(set().union(*(b.keys() for b in odds_by_book.values())))
            rows = []
            for player in all_players:
                row = {"Player": player}
                best = None
                for book in books:
                    odds = odds_by_book[book].get(player)
                    if odds is not None:
                        if odds_format == "Decimal":
                            row[book] = round(american_to_decimal(odds), 2)
                        else:
                            row[book] = f"+{odds}" if odds > 0 else str(odds)
                        if best is None or odds > best:
                            best = odds
                    else:
                        row[book] = ""
                all_odds = {b: odds_by_book[b][player] for b in books if player in odds_by_book[b]}
                if all_odds:
                    fair_probs = remove_vig(all_odds)
                    avg_fair = sum(fair_probs.values()) / len(fair_probs)
                    row["Fair Prob"] = f"{avg_fair:.1%}"
                    row["Best Line"] = f"+{best}" if best and best > 0 else str(best)
                rows.append(row)

            df_odds = pd.DataFrame(rows)
            df_odds["_sort"] = df_odds["Fair Prob"].apply(
                lambda x: float(x.strip("%")) if isinstance(x, str) and "%" in x else 0
            )
            df_odds = df_odds.sort_values("_sort", ascending=False).drop(columns="_sort")
            st.subheader(f"Outright Winner Odds - {len(books)} Sportsbooks")
            st.dataframe(df_odds, use_container_width=True, hide_index=True, height=600)
            if odds_api.remaining_credits is not None:
                st.caption(f"API credits remaining: {odds_api.remaining_credits}")
        else:
            st.warning("No odds data. Check ODDS_API_KEY in secrets.")
    except Exception as e:
        st.error(f"Error fetching odds: {e}")

# ── Tab 3: +EV Finder ───────────────────────────────────────────────────────

with tab_ev:
    try:
        if odds_by_book and leaderboard:
            profiles = build_profiles_from_data(leaderboard, rankings)
            if run_monte_carlo and profiles:
                st.info("Running 50,000 tournament simulations...")
                mc_results = monte_carlo_tournament(profiles, n_simulations=50000)
                predictions = {name: r["win"] for name, r in mc_results.items()}
            else:
                scores = compute_composite_scores(profiles)
                predictions = scores_to_probabilities(scores)

            ev_bets = find_ev_bets(predictions, odds_by_book, market="outright", min_ev=min_ev)

            if ev_bets:
                st.subheader(f"{len(ev_bets)} Positive EV Opportunities")
                rows = []
                for bet in ev_bets:
                    ks = kelly_bet_size(bankroll, bet.model_prob, bet.best_odds,
                                        fraction=kelly_fraction, max_pct=max_bet_pct)
                    rows.append({
                        "Player": bet.player, "Best Book": bet.best_book,
                        "Best Odds": f"+{bet.best_odds}" if bet.best_odds > 0 else str(bet.best_odds),
                        "Implied Prob": f"{bet.implied_prob:.1%}",
                        "Model Prob": f"{bet.model_prob:.1%}",
                        "Edge": f"{bet.edge:.1%}",
                        "EV / $1": f"${bet.ev_per_dollar:.3f}",
                        "Kelly Bet": f"${ks:.2f}",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

                fig = go.Figure()
                fig.add_trace(go.Bar(
                    x=[b.player for b in ev_bets[:20]],
                    y=[b.edge * 100 for b in ev_bets[:20]],
                    marker_color=["#00C853" if b.edge > 0.05 else "#FFC107" for b in ev_bets[:20]],
                    text=[f"{b.edge:.1%}" for b in ev_bets[:20]],
                    textposition="outside",
                ))
                fig.update_layout(title="Model Edge vs Market (Top 20)",
                                  xaxis_title="Player", yaxis_title="Edge (%)",
                                  template="plotly_dark", height=400)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info(f"No +EV bets above {min_ev:.0%} threshold.")

            if predictions:
                st.subheader("Model vs Market Probabilities")
                comparison = []
                for name in sorted(predictions.keys(), key=lambda n: predictions[n], reverse=True)[:30]:
                    model_p = predictions[name]
                    market_p = american_to_implied_prob(best_odds_map[name]) if name in best_odds_map else None
                    if market_p:
                        comparison.append({"Player": name, "Model": model_p, "Market": market_p})
                if comparison:
                    df_cmp = pd.DataFrame(comparison)
                    fig2 = go.Figure()
                    fig2.add_trace(go.Bar(name="Model", x=df_cmp["Player"], y=df_cmp["Model"]*100, marker_color="#00C853"))
                    fig2.add_trace(go.Bar(name="Market", x=df_cmp["Player"], y=df_cmp["Market"]*100, marker_color="#FF5252"))
                    fig2.update_layout(barmode="group", title="Win Probability: Model vs Market (Top 30)",
                                       yaxis_title="Win Prob (%)", template="plotly_dark", height=500)
                    st.plotly_chart(fig2, use_container_width=True)
        elif not odds_by_book:
            st.warning("No odds data available.")
        else:
            st.info("Waiting for leaderboard data...")
    except Exception as e:
        st.error(f"Error in EV analysis: {e}")

# ── Tab 4: Model Details ────────────────────────────────────────────────────

with tab_model:
    try:
        if leaderboard:
            profiles = build_profiles_from_data(leaderboard, rankings)
            if run_monte_carlo and profiles:
                mc_results = monte_carlo_tournament(profiles, n_simulations=50000, seed=42)
                st.subheader("Monte Carlo Results (50K sims)")
                rows = []
                for name, r in sorted(mc_results.items(), key=lambda x: x[1]["win"], reverse=True)[:40]:
                    rows.append({
                        "Player": name,
                        "Win %": f"{r['win']:.2%}", "Top 5 %": f"{r['top5']:.1%}",
                        "Top 10 %": f"{r['top10']:.1%}", "Top 20 %": f"{r['top20']:.1%}",
                        "Make Cut %": f"{r['make_cut']:.1%}", "Avg Finish": f"{r['avg_finish']:.1f}",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=500)

                top_players = sorted(mc_results.items(), key=lambda x: x[1]["win"], reverse=True)[:15]
                fig = go.Figure()
                for market, color in [("win","#00C853"),("top5","#FFC107"),("top10","#2196F3"),("top20","#9C27B0")]:
                    fig.add_trace(go.Bar(name=market.title(), x=[p[0] for p in top_players],
                                         y=[p[1][market]*100 for p in top_players], marker_color=color))
                fig.update_layout(barmode="group", title="Probability Distribution (Top 15)",
                                  yaxis_title="Probability (%)", template="plotly_dark", height=500)
                st.plotly_chart(fig, use_container_width=True)

            if profiles:
                st.subheader("Strokes Gained Radar")
                selected = st.multiselect("Select players to compare", [p.name for p in profiles],
                                           default=[p.name for p in sorted(profiles, key=lambda x: x.world_ranking)[:3]])
                if selected:
                    categories = ["SG Total","SG Off Tee","SG Approach","SG Around Green","SG Putting"]
                    fig_r = go.Figure()
                    for name in selected:
                        p = next((p for p in profiles if p.name == name), None)
                        if p:
                            vals = [p.sg_total, p.sg_off_tee, p.sg_approach, p.sg_around_green, p.sg_putting]
                            fig_r.add_trace(go.Scatterpolar(r=vals+[vals[0]], theta=categories+[categories[0]], name=name))
                    fig_r.update_layout(polar=dict(radialaxis=dict(visible=True)), template="plotly_dark", height=500)
                    st.plotly_chart(fig_r, use_container_width=True)
        else:
            st.info("No leaderboard data available.")
    except Exception as e:
        st.error(f"Error in model tab: {e}")

# ── Tab 5: Bet Slip ──────────────────────────────────────────────────────────

with tab_betslip:
    st.subheader("Create a Bet")

    if not odds_by_book:
        st.warning("No odds data available to create bets.")
    else:
        players_with_odds = sorted(player_book_odds.keys())

        col1, col2 = st.columns([2, 1])

        with col1:
            # Bet creation form
            sel_player = st.selectbox("Player", players_with_odds, key="bs_player")
            sel_market = st.selectbox("Market", ["Outright Winner", "Top 5", "Top 10", "Top 20"], key="bs_market")

            # Show available odds across books for selected player
            if sel_player and sel_player in player_book_odds:
                player_odds = player_book_odds[sel_player]
                avail_books = sorted(player_odds.keys())
                sel_book = st.selectbox("Sportsbook", avail_books, key="bs_book")
                sel_odds = player_odds.get(sel_book, 0)

                st.markdown(f"**Odds: +{sel_odds}**" if sel_odds > 0 else f"**Odds: {sel_odds}**")

                sel_stake = st.number_input("Stake ($)", value=25.0, min_value=1.0, step=5.0, key="bs_stake")

                # Calculate payouts
                decimal_odds = american_to_decimal(sel_odds)
                potential_payout = sel_stake * decimal_odds
                potential_profit = potential_payout - sel_stake

                # Model info if available
                model_prob = None
                ev_val = None
                try:
                    profiles = build_profiles_from_data(leaderboard, rankings)
                    scores = compute_composite_scores(profiles)
                    probs = scores_to_probabilities(scores)
                    model_prob = probs.get(sel_player, 0)
                    ev_val = ev_from_american(model_prob, sel_odds) if model_prob else None
                except Exception:
                    pass

                kelly_rec = kelly_bet_size(bankroll, model_prob or 0.01, sel_odds,
                                           fraction=kelly_fraction, max_pct=max_bet_pct)

        with col2:
            # Bet card preview
            if sel_player and sel_odds:
                ev_class = "positive" if (ev_val and ev_val > 0) else "negative"
                ev_badge = ""
                if ev_val is not None:
                    badge_class = "" if ev_val > 0 else "neg"
                    ev_badge = f'<span class="ev-badge {badge_class}">EV: ${ev_val:.3f}</span>'

                odds_display = f"+{sel_odds}" if sel_odds > 0 else str(sel_odds)

                st.markdown(f"""
                <div class="bet-card {ev_class}">
                    <div class="player">{sel_player} {ev_badge}</div>
                    <div class="detail">{sel_market} | {sel_book} | {odds_display}</div>
                    <div class="payout">Payout: ${potential_payout:,.2f}</div>
                    <div class="profit">Profit: ${potential_profit:,.2f}</div>
                    <div class="stake-info">Stake: ${sel_stake:.2f} | Kelly suggests: ${kelly_rec:.2f}</div>
                    <div class="detail" style="margin-top:6px">
                        Model: {f'{model_prob:.1%}' if model_prob else 'N/A'} |
                        Implied: {american_to_implied_prob(sel_odds):.1%} |
                        Decimal: {decimal_odds:.2f}x
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Payout table for different stakes
                st.markdown("**Quick Payout Calculator**")
                stakes = [10, 25, 50, 100, 250, 500]
                payout_rows = [{"Stake": f"${s}", "Payout": f"${s * decimal_odds:,.2f}",
                                "Profit": f"${s * (decimal_odds-1):,.2f}"} for s in stakes]
                st.dataframe(pd.DataFrame(payout_rows), use_container_width=True, hide_index=True)

        # Place bet button
        if sel_player and sel_odds:
            if st.button("Place Bet", type="primary", key="bs_place"):
                market_key = sel_market.lower().replace(" ", "")
                bet_id = place_bet(
                    player_name=sel_player, sport="golf",
                    event_name="Masters Tournament 2026",
                    market=market_key, sportsbook=sel_book,
                    american_odds=sel_odds, stake=sel_stake,
                    model_prob=model_prob, ev=ev_val,
                )
                st.success(f"Bet #{bet_id} placed: {sel_player} {sel_market} @ +{sel_odds} for ${sel_stake:.2f}")
                st.rerun()

    # ── Active Bet Cards ─────────────────────────────────────────────────────

    st.divider()
    st.subheader("Active Bets")

    all_bets = get_bet_history(sport="golf")
    pending_bets = [b for b in all_bets if b["result"] == "pending"]
    settled_bets = [b for b in all_bets if b["result"] != "pending"]

    if pending_bets:
        for bet in pending_bets:
            odds_val = bet["american_odds"]
            dec = american_to_decimal(odds_val)
            payout = bet["stake"] * dec
            profit = payout - bet["stake"]
            odds_str = f"+{odds_val}" if odds_val > 0 else str(odds_val)

            col_card, col_actions = st.columns([3, 1])

            with col_card:
                st.markdown(f"""
                <div class="bet-card pending">
                    <div class="player">{bet['player_name']}</div>
                    <div class="detail">{bet['market']} | {bet['sportsbook']} | {odds_str}</div>
                    <div class="payout">Payout: ${payout:,.2f}</div>
                    <div class="profit">Profit: ${profit:,.2f}</div>
                    <div class="stake-info">Stake: ${bet['stake']:.2f} | Placed: {bet['placed_at'][:16] if bet['placed_at'] else ''}</div>
                </div>
                """, unsafe_allow_html=True)

            with col_actions:
                st.write("")  # spacer
                st.write("")
                c1, c2, c3 = st.columns(3)
                with c1:
                    if st.button("Win", key=f"w_{bet['id']}"):
                        settle_bet(bet["id"], "win", payout)
                        st.rerun()
                with c2:
                    if st.button("Loss", key=f"l_{bet['id']}"):
                        settle_bet(bet["id"], "loss")
                        st.rerun()
                with c3:
                    if st.button("Push", key=f"p_{bet['id']}"):
                        settle_bet(bet["id"], "push", bet["stake"])
                        add_bankroll_entry("bet_push", bet["stake"], bet["id"])
                        st.rerun()
    else:
        st.caption("No active bets. Create one above.")

    # Show recent settled bets
    if settled_bets:
        with st.expander(f"Settled Bets ({len(settled_bets)})"):
            for bet in settled_bets[:10]:
                result_color = {"win": "#00C853", "loss": "#FF5252", "push": "#FFC107"}.get(bet["result"], "#888")
                odds_str = f"+{bet['american_odds']}" if bet["american_odds"] > 0 else str(bet["american_odds"])
                payout_str = ""
                if bet.get("payout"):
                    payout_val = bet["payout"]
                    payout_str = f" | Payout: ${payout_val:.2f}"
                st.markdown(
                    f"**{bet['player_name']}** | {bet['market']} | {odds_str} | "
                    f"${bet['stake']:.2f} | "
                    f"<span style='color:{result_color};font-weight:700'>{bet['result'].upper()}</span>"
                    f"{payout_str}",
                    unsafe_allow_html=True,
                )

# ── Tab 6: Parlay Builder ───────────────────────────────────────────────────

# Market definitions with descriptions
PARLAY_MARKETS = {
    "Top 5 Finish": {"key": "top5", "desc": "Player finishes in the top 5"},
    "Top 10 Finish": {"key": "top10", "desc": "Player finishes in the top 10"},
    "Top 20 Finish": {"key": "top20", "desc": "Player finishes in the top 20"},
    "Make the Cut": {"key": "make_cut", "desc": "Player makes the weekend cut"},
    "Outright Winner": {"key": "win", "desc": "Player wins the tournament"},
}

# Rough odds multipliers for non-outright markets (since API only gives outrights)
# These approximate typical sportsbook pricing for placement markets
MARKET_ODDS_FACTOR = {
    "win": 1.0,        # use actual outright odds
    "top5": 0.18,      # ~5x shorter than outright
    "top10": 0.30,     # ~3x shorter
    "top20": 0.50,     # ~2x shorter
    "make_cut": 0.70,  # much shorter
}

with tab_parlay:
    st.subheader("Build a Parlay")
    st.caption(
        "Select a market for each leg. Top 5/10/20 and Make Cut bets can all hit "
        "in the same tournament — unlike outright winners where only one can win."
    )

    if not odds_by_book:
        st.warning("No odds data available.")
    else:
        if "parlay_legs" not in st.session_state:
            st.session_state.parlay_legs = []

        # ── Add a leg ────────────────────────────────────────────────────

        col_add, col_preview = st.columns([2, 1])

        with col_add:
            players_sorted = sorted(player_book_odds.keys())
            p_sel = st.selectbox("Player", players_sorted, key="par_player")
            p_market = st.selectbox("Market", list(PARLAY_MARKETS.keys()), index=1, key="par_market")
            market_key = PARLAY_MARKETS[p_market]["key"]

            if p_sel and p_sel in player_book_odds:
                p_books = sorted(player_book_odds[p_sel].keys())
                best_book = max(p_books, key=lambda b: player_book_odds[p_sel][b])
                p_book = st.selectbox("Sportsbook", p_books,
                                       index=p_books.index(best_book), key="par_book")
                outright_odds = player_book_odds[p_sel][p_book]

                # Estimate odds for non-outright markets
                if market_key == "win":
                    leg_odds = outright_odds
                else:
                    # Convert outright odds to placement odds
                    outright_prob = american_to_implied_prob(outright_odds)
                    factor = MARKET_ODDS_FACTOR[market_key]
                    # Approximate: top-N prob is roughly outright_prob / factor_ratio
                    placement_prob = min(outright_prob / factor + (1 - 1/factor) * 0.5, 0.85)
                    placement_prob = max(placement_prob, outright_prob)
                    from utils.odds_math import implied_prob_to_american
                    try:
                        leg_odds = implied_prob_to_american(placement_prob)
                    except ValueError:
                        leg_odds = -200

                odds_display = f"+{leg_odds}" if leg_odds > 0 else str(leg_odds)
                dec_display = american_to_decimal(leg_odds)

                # Get model probability for this market
                model_market_prob = None
                try:
                    profiles = build_profiles_from_data(leaderboard, rankings)
                    mc = monte_carlo_tournament(profiles, n_simulations=10000, seed=42)
                    if p_sel in mc:
                        model_market_prob = mc[p_sel].get(market_key, 0)
                except Exception:
                    pass

                st.markdown(f"""
                <div class="parlay-leg">
                    <span class="leg-player">{p_sel}</span>
                    <span class="leg-odds" style="float:right">{odds_display} ({dec_display:.2f}x)</span>
                    <div style="color:#888;font-size:0.8rem">{p_market} | {p_book}
                    {f' | Model: {model_market_prob:.1%}' if model_market_prob else ''}</div>
                </div>
                """, unsafe_allow_html=True)

                if st.button("Add to Parlay", key="par_add"):
                    # Check: warn if adding outright winner when one already exists
                    existing_outrights = [l for l in st.session_state.parlay_legs if l["market_key"] == "win"]
                    if market_key == "win" and existing_outrights:
                        st.warning("Only one player can win — consider using Top 5/10/20 instead.")
                    else:
                        st.session_state.parlay_legs.append({
                            "player": p_sel, "book": p_book, "odds": leg_odds,
                            "market": p_market, "market_key": market_key,
                            "model_prob": model_market_prob,
                        })
                        st.rerun()

        with col_preview:
            st.markdown("**Parlay Legs**")
            if st.session_state.parlay_legs:
                for i, leg in enumerate(st.session_state.parlay_legs):
                    odds_str = f"+{leg['odds']}" if leg['odds'] > 0 else str(leg['odds'])
                    st.markdown(f"""
                    <div class="parlay-leg">
                        <span class="leg-player">{leg['player']}</span>
                        <span class="leg-odds" style="float:right">{odds_str}</span>
                        <div style="color:#888;font-size:0.8rem">{leg['market']} | {leg['book']}</div>
                    </div>
                    """, unsafe_allow_html=True)

                # Remove individual legs
                if len(st.session_state.parlay_legs) > 0:
                    remove_idx = st.selectbox("Remove leg", range(len(st.session_state.parlay_legs)),
                                               format_func=lambda i: st.session_state.parlay_legs[i]["player"],
                                               key="par_remove_sel")
                    col_rm, col_clr = st.columns(2)
                    with col_rm:
                        if st.button("Remove", key="par_remove"):
                            st.session_state.parlay_legs.pop(remove_idx)
                            st.rerun()
                    with col_clr:
                        if st.button("Clear All", key="par_clear"):
                            st.session_state.parlay_legs = []
                            st.rerun()
            else:
                st.caption("No legs added yet. Pick a player and market above.")

        # ── Parlay card + payout calc ────────────────────────────────────

        if len(st.session_state.parlay_legs) >= 2:
            st.divider()

            legs = st.session_state.parlay_legs
            combined_decimal = parlay_decimal_odds([american_to_decimal(l["odds"]) for l in legs])
            combined_american = parlay_american_odds([l["odds"] for l in legs])

            # Joint probability from model
            joint_prob = 1.0
            for leg in legs:
                lp = leg.get("model_prob")
                if lp and lp > 0:
                    joint_prob *= lp
                else:
                    joint_prob *= 0.01
            if joint_prob >= 1:
                joint_prob = None

            parlay_ev = None
            if joint_prob:
                parlay_ev = (joint_prob * (combined_decimal - 1)) - ((1 - joint_prob) * 1.0)

            parlay_stake = st.number_input("Parlay Stake ($)", value=10.0, min_value=1.0,
                                            step=5.0, key="par_stake")
            parlay_payout = parlay_stake * combined_decimal
            parlay_profit = parlay_payout - parlay_stake

            # Build bet card HTML
            ev_class = "positive" if (parlay_ev and parlay_ev > 0) else "negative"
            ev_badge = ""
            if parlay_ev is not None:
                badge_class = "" if parlay_ev > 0 else "neg"
                ev_badge = f'<span class="ev-badge {badge_class}">EV: ${parlay_ev:.3f}</span>'

            am_str = f"+{combined_american}" if combined_american > 0 else str(combined_american)
            jp_str = f"{joint_prob:.4%}" if joint_prob else "N/A"

            legs_html = ""
            for leg in legs:
                o = f"+{leg['odds']}" if leg['odds'] > 0 else str(leg['odds'])
                mp = f" | Model: {leg['model_prob']:.1%}" if leg.get('model_prob') else ""
                legs_html += f"""
                <div class="parlay-leg">
                    <span class="leg-player">{leg['player']}</span>
                    <span class="leg-odds" style="float:right">{o}</span>
                    <div style="color:#888;font-size:0.8rem">{leg['market']} | {leg['book']}{mp}</div>
                </div>"""

            st.markdown(f"""
            <div class="bet-card parlay">
                <div class="player">{len(legs)}-Leg Parlay {ev_badge}</div>
                <div class="detail">Combined: {am_str} ({combined_decimal:.1f}x) | Joint Prob: {jp_str}</div>
                {legs_html}
                <div class="payout" style="margin-top:12px">Payout: ${parlay_payout:,.2f}</div>
                <div class="profit">Profit: ${parlay_profit:,.2f}</div>
                <div class="stake-info">Stake: ${parlay_stake:.2f}</div>
            </div>
            """, unsafe_allow_html=True)

            # KPI metrics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Combined Odds", f"{combined_decimal:.1f}x")
            with col2:
                st.metric("Payout", f"${parlay_payout:,.2f}")
            with col3:
                st.metric("Profit", f"${parlay_profit:,.2f}")
            with col4:
                if joint_prob:
                    kelly_p = kelly_bet_size(bankroll, joint_prob, combined_american,
                                             fraction=kelly_fraction, max_pct=max_bet_pct)
                    st.metric("Kelly Bet", f"${kelly_p:.2f}")

            # Payout table
            st.markdown("**Payout Calculator**")
            stakes = [5, 10, 25, 50, 100, 250]
            payout_rows = [{"Stake": f"${s}", "Payout": f"${s * combined_decimal:,.2f}",
                            "Profit": f"${s * (combined_decimal-1):,.2f}"} for s in stakes]
            st.dataframe(pd.DataFrame(payout_rows), use_container_width=True, hide_index=True)

            # Place parlay button
            if st.button("Place Parlay", type="primary", key="par_place"):
                leg_parts = []
                for l in legs:
                    o = f"+{l['odds']}" if l['odds'] > 0 else str(l['odds'])
                    leg_parts.append(f"{l['player']} {l['market']} ({o})")
                leg_desc = " + ".join(leg_parts)
                bet_id = place_bet(
                    player_name=f"PARLAY: {', '.join(l['player'] + ' ' + l['market'] for l in legs)}",
                    sport="golf", event_name="Masters Tournament 2026",
                    market="parlay", sportsbook="Multi",
                    american_odds=combined_american, stake=parlay_stake,
                    model_prob=joint_prob, ev=parlay_ev,
                )
                st.success(f"Parlay #{bet_id} placed: {leg_desc}")
                st.success(f"Stake: ${parlay_stake:.2f} | Payout: ${parlay_payout:,.2f}")
                st.session_state.parlay_legs = []
                st.rerun()

        elif len(st.session_state.parlay_legs) == 1:
            st.info("Add at least 2 legs to build a parlay.")
