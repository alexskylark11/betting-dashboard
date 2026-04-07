# Betting Dashboard — CLAUDE.md

## Project Overview
Streamlit multi-page sports betting dashboard covering Golf, NFL, and Horse Racing. Scrapes performance data, monitors betting lines across sportsbooks, and optimizes betting strategy using EV analysis, Monte Carlo simulation, and Kelly criterion sizing.

## Commands
```bash
# Install dependencies
python -m pip install -r requirements.txt

# Run dashboard
streamlit run app.py

# Run tests
python tests/test_odds_math.py
```

## Architecture
- `app.py` — Streamlit home page with bankroll overview and sport navigation
- `pages/` — Multi-page Streamlit (1_Masters, 2_Golf_Model, 3_NFL, 4_Horse_Racing, 5_Parlay_Builder, 6_Bankroll)
- `scrapers/` — Data fetchers (ESPN API, The Odds API) with ScraperBase for retry/rate-limit
- `models/` — Betting math (EV calculator, Kelly criterion, parlay optimizer, golf prediction model)
- `utils/` — Odds math (American/decimal conversion, vig removal), JSON file cache
- `db/` — SQLite via raw sqlite3 (players, odds_snapshots, golf_stats, course_history, bets, bankroll)

## Data Sources
- **ESPN API** (free, no auth) — live leaderboard, field, world rankings
- **The Odds API** (free tier, 500 req/month) — outright odds from DK, FanDuel, BetMGM, etc.
- **HRL Racing Monitor** — horse racing data bridged from sibling project

## Environment Variables (.env)
```
ODDS_API_KEY=your_key_from_the-odds-api.com
DB_PATH=data/betting.db
```

## Key Models
- **Golf Model**: Weighted composite (SG, course history, rankings, recent form) → softmax probabilities
- **Monte Carlo**: 50K tournament sims for top-5/10/20 probability distributions
- **EV Calculator**: model_prob * (decimal_odds - 1) - (1 - model_prob)
- **Kelly Criterion**: Quarter-Kelly default, 5% bankroll cap per bet
- **Parlay Optimizer**: Correlation-aware joint probability for multi-leg parlays
