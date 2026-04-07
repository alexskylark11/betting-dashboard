"""NFL Dashboard — scores, odds, and line comparison."""

import streamlit as st
import pandas as pd
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.models import init_db
from scrapers.espn import ESPNScraper
from scrapers.odds_api import OddsAPIScraper

init_db()

st.set_page_config(page_title="NFL", page_icon="🏈", layout="wide")
st.markdown("# 🏈 NFL Dashboard")

espn = ESPNScraper()
odds_api = OddsAPIScraper()

tab_scores, tab_odds = st.tabs(["📋 Scores & Schedule", "💰 Odds"])

# ── Tab 1: Scores ────────────────────────────────────────────────────────────

with tab_scores:
    try:
        scoreboard = espn.get_nfl_scoreboard()
        events = scoreboard.get("events", [])

        if events:
            st.subheader(f"{scoreboard.get('leagues', [{}])[0].get('name', 'NFL')} — "
                        f"{scoreboard.get('week', {}).get('text', '')}")

            for event in events:
                competitions = event.get("competitions", [])
                for comp in competitions:
                    competitors = comp.get("competitors", [])
                    if len(competitors) == 2:
                        away = competitors[1] if competitors[0].get("homeAway") == "home" else competitors[0]
                        home = competitors[0] if competitors[0].get("homeAway") == "home" else competitors[1]

                        away_name = away.get("team", {}).get("displayName", "Away")
                        home_name = home.get("team", {}).get("displayName", "Home")
                        away_score = away.get("score", "")
                        home_score = home.get("score", "")
                        status = comp.get("status", {}).get("type", {}).get("shortDetail", "")

                        col1, col2, col3 = st.columns([2, 1, 2])
                        with col1:
                            st.write(f"**{away_name}** {away_score}")
                        with col2:
                            st.caption(status)
                        with col3:
                            st.write(f"**{home_name}** {home_score}")
                        st.divider()
        else:
            st.info("No NFL games currently scheduled. Check back during the season (September–February).")
    except Exception as e:
        st.error(f"Error fetching NFL data: {e}")

# ── Tab 2: Odds ──────────────────────────────────────────────────────────────

with tab_odds:
    market = st.selectbox("Market", ["Spreads", "Moneyline", "Totals"])
    market_map = {"Spreads": "spreads", "Moneyline": "h2h", "Totals": "totals"}

    try:
        raw = odds_api.get_odds("americanfootball_nfl", markets=market_map[market])
        if raw:
            for event_data in raw:
                game_name = event_data.get("home_team", "") + " vs " + event_data.get("away_team", "")
                st.subheader(game_name)

                rows = []
                for bookmaker in event_data.get("bookmakers", []):
                    book = bookmaker.get("title", "")
                    for mkt in bookmaker.get("markets", []):
                        for outcome in mkt.get("outcomes", []):
                            row = {
                                "Sportsbook": book,
                                "Team": outcome.get("name", ""),
                                "Odds": outcome.get("price", ""),
                            }
                            if "point" in outcome:
                                row["Spread/Total"] = outcome["point"]
                            rows.append(row)

                if rows:
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
                st.divider()
        else:
            st.info("No NFL odds available. Check back during the season or verify your API key.")
    except Exception as e:
        st.error(f"Error fetching NFL odds: {e}")
