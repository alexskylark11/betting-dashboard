"""Horse Racing Dashboard — bridges to hrl-racing-monitor data."""

import streamlit as st
import pandas as pd
import sqlite3
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.models import init_db

init_db()

st.set_page_config(page_title="Horse Racing", page_icon="🏇", layout="wide")
st.markdown("# 🏇 Horse Racing")

# ── Bridge to hrl-racing-monitor DB ─────────────────────────────────────────

HRL_DB_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "hrl-racing-monitor", "data", "hrl_ratings.db"
)

if os.path.exists(HRL_DB_PATH):
    st.success("Connected to HRL Racing Monitor database")

    con = sqlite3.connect(HRL_DB_PATH)
    con.row_factory = sqlite3.Row

    tab_ratings, tab_performance, tab_value = st.tabs([
        "📊 Ratings", "🏁 Performance", "💰 Value Overlay"
    ])

    with tab_ratings:
        st.subheader("Top Rated Horses")
        rows = con.execute("""
            SELECT h.name, h.trainer, h.sire,
                   r.total_score, r.hrl_classification,
                   r.race_performance_score, r.pedigree_score,
                   r.computed_at
            FROM ratings r
            JOIN horses h ON h.id = r.horse_id
            ORDER BY r.total_score DESC
            LIMIT 50
        """).fetchall()

        if rows:
            df = pd.DataFrame([dict(r) for r in rows])
            df.columns = ["Name", "Trainer", "Sire", "Total Score", "Classification",
                          "Race Perf", "Pedigree", "Rated At"]

            # Color code classification
            def color_class(val):
                colors = {"A": "#00C853", "B": "#FFC107", "C": "#FF9800", "D": "#FF5252"}
                for key, color in colors.items():
                    if key in str(val):
                        return f"color: {color}"
                return ""

            st.dataframe(df, use_container_width=True, hide_index=True, height=500)
        else:
            st.info("No ratings found. Run the HRL rating engine first.")

    with tab_performance:
        st.subheader("Speed Figures & Race Performance")
        perf_rows = con.execute("""
            SELECT h.name, h.trainer,
                   rp.starts, rp.wins, rp.places, rp.shows,
                   rp.best_speed_fig, rp.last_speed_fig, rp.avg_last_3_speed_fig,
                   rp.earnings, rp.win_rate, rp.itm_rate
            FROM race_performance rp
            JOIN horses h ON h.id = rp.horse_id
            WHERE rp.best_speed_fig > 0
            ORDER BY rp.best_speed_fig DESC
            LIMIT 50
        """).fetchall()

        if perf_rows:
            df_perf = pd.DataFrame([dict(r) for r in perf_rows])
            df_perf.columns = ["Name", "Trainer", "Starts", "Wins", "Places", "Shows",
                               "Best Fig", "Last Fig", "Avg L3 Fig", "Earnings",
                               "Win %", "ITM %"]
            st.dataframe(df_perf, use_container_width=True, hide_index=True, height=500)
        else:
            st.info("No performance data available.")

    with tab_value:
        st.subheader("Value Overlay — Speed Figs vs Odds")
        st.info(
            "This feature compares HRL speed figures against morning line odds to find "
            "value plays. Currently requires race-day odds data.\n\n"
            "**Coming soon:** Integration with The Racing API for live odds comparison."
        )

        # Placeholder for when we add odds data
        if perf_rows:
            import plotly.express as px
            df_val = pd.DataFrame([dict(r) for r in perf_rows])
            fig = px.scatter(
                df_val,
                x="best_speed_fig",
                y="earnings",
                hover_name="name",
                size="starts",
                color="win_rate",
                color_continuous_scale="Viridis",
                title="Speed Figure vs Earnings",
            )
            fig.update_layout(template="plotly_dark", height=500)
            st.plotly_chart(fig, use_container_width=True)

    con.close()
else:
    st.warning(
        "HRL Racing Monitor database not found.\n\n"
        f"Expected at: `{HRL_DB_PATH}`\n\n"
        "Run the HRL Racing Monitor first to populate horse racing data, "
        "or update the path in this file."
    )
    st.divider()
    st.info(
        "**Horse Racing Betting Features (Planned):**\n"
        "- Live odds from The Racing API\n"
        "- Speed figure value overlay\n"
        "- Trainer/jockey analytics\n"
        "- Morning line vs closing line comparison"
    )
