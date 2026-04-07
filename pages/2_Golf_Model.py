"""Golf Model Tuning — adjust weights and see how predictions change."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.models import init_db
from scrapers.espn import ESPNScraper
from models.golf_model import (
    GolferProfile, DEFAULT_WEIGHTS, compute_composite_scores,
    scores_to_probabilities, monte_carlo_tournament, build_profiles_from_data,
)

init_db()

st.set_page_config(page_title="Golf Model", page_icon="🧠", layout="wide")
st.markdown("# 🧠 Golf Model Tuning")

espn = ESPNScraper()

# ── Weight Sliders ───────────────────────────────────────────────────────────

st.sidebar.header("Model Weights")
st.sidebar.caption("Adjust weights (auto-normalized to sum to 1.0)")

weights = {}
for key, default in DEFAULT_WEIGHTS.items():
    label = key.replace("_", " ").title()
    weights[key] = st.sidebar.slider(label, 0.0, 1.0, default, 0.05)

# Normalize
total_w = sum(weights.values())
if total_w > 0:
    weights = {k: v / total_w for k, v in weights.items()}

st.sidebar.divider()
temperature = st.sidebar.slider("Softmax Temperature", 0.05, 0.50, 0.15, 0.01,
                                 help="Lower = more peaked (favorites get more probability)")
n_sims = st.sidebar.select_slider("Monte Carlo Sims", [5000, 10000, 25000, 50000], value=25000)

# ── Show Current Weights ─────────────────────────────────────────────────────

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("Active Weights")
    for k, v in weights.items():
        st.write(f"**{k.replace('_', ' ').title()}**: {v:.0%}")

# ── Run Model ────────────────────────────────────────────────────────────────

with col2:
    try:
        leaderboard = espn.get_golf_leaderboard()
        rankings = []
        try:
            rankings = espn.get_golf_rankings()
        except Exception:
            pass

        if leaderboard:
            profiles = build_profiles_from_data(leaderboard, rankings)
            scores = compute_composite_scores(profiles, weights)
            probs = scores_to_probabilities(scores, temperature=temperature)

            mc_results = monte_carlo_tournament(profiles, n_simulations=n_sims, seed=42)

            st.subheader("Model Predictions")

            rows = []
            for name in sorted(probs.keys(), key=lambda n: probs[n], reverse=True)[:30]:
                mc = mc_results.get(name, {})
                rows.append({
                    "Player": name,
                    "Composite Score": f"{scores.get(name, 0):.3f}",
                    "Softmax Win %": f"{probs[name]:.2%}",
                    "MC Win %": f"{mc.get('win', 0):.2%}",
                    "MC Top 5": f"{mc.get('top5', 0):.1%}",
                    "MC Top 10": f"{mc.get('top10', 0):.1%}",
                    "MC Top 20": f"{mc.get('top20', 0):.1%}",
                })

            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True, height=500)

            # Weight sensitivity chart
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=list(weights.keys()),
                y=[v * 100 for v in weights.values()],
                marker_color="#00C853",
                text=[f"{v:.0%}" for v in weights.values()],
                textposition="outside",
            ))
            fig.update_layout(
                title="Weight Distribution",
                yaxis_title="Weight (%)",
                template="plotly_dark",
                height=350,
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No tournament data available from ESPN.")
    except Exception as e:
        st.error(f"Error: {e}")
