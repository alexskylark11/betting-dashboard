"""Golf prediction model — weighted composite + Monte Carlo tournament simulation."""

import numpy as np
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class GolferProfile:
    name: str
    sg_total: float = 0.0
    sg_tee_to_green: float = 0.0
    sg_approach: float = 0.0
    sg_putting: float = 0.0
    sg_off_tee: float = 0.0
    sg_around_green: float = 0.0
    world_ranking: int = 200
    recent_form: float = 0.0          # avg finish position last 4 events (lower = better)
    course_history_score: float = 0.0  # 0-1 score based on past finishes at course
    consistency: float = 2.0           # std dev of recent scores (higher = more volatile)


# Default model weights — tunable via the UI
DEFAULT_WEIGHTS = {
    "sg_total": 0.25,
    "sg_tee_to_green": 0.15,
    "course_history": 0.20,
    "recent_form": 0.15,
    "world_ranking": 0.10,
    "sg_approach": 0.10,
    "sg_putting": 0.05,
}


def _normalize(values: List[float]) -> List[float]:
    """Min-max normalize to 0-1 range."""
    if not values:
        return values
    mn, mx = min(values), max(values)
    if mx == mn:
        return [0.5] * len(values)
    return [(v - mn) / (mx - mn) for v in values]


def compute_composite_scores(
    golfers: List[GolferProfile],
    weights: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """Compute weighted composite score for each golfer.

    Returns {name: composite_score} where higher = better.
    """
    w = weights or DEFAULT_WEIGHTS

    if not golfers:
        return {}

    # Raw feature vectors
    features = {
        "sg_total": [g.sg_total for g in golfers],
        "sg_tee_to_green": [g.sg_tee_to_green for g in golfers],
        "course_history": [g.course_history_score for g in golfers],
        "recent_form": [-g.recent_form for g in golfers],  # negative: lower = better
        "world_ranking": [-g.world_ranking for g in golfers],  # negative: lower = better
        "sg_approach": [g.sg_approach for g in golfers],
        "sg_putting": [g.sg_putting for g in golfers],
    }

    # Normalize each feature to 0-1
    normalized = {k: _normalize(v) for k, v in features.items()}

    # Weighted composite
    scores = {}
    for i, golfer in enumerate(golfers):
        score = sum(w.get(k, 0) * normalized[k][i] for k in w)
        scores[golfer.name] = score

    return scores


def scores_to_probabilities(
    scores: Dict[str, float],
    temperature: float = 0.15,
) -> Dict[str, float]:
    """Convert composite scores to win probabilities via softmax.

    Temperature controls how peaked the distribution is:
    - Lower temp = favorites get more probability mass
    - Higher temp = more even distribution
    - Tune so top favorite gets ~12-18% for a major (realistic)
    """
    names = list(scores.keys())
    vals = np.array([scores[n] for n in names])

    # Softmax with temperature
    exp_vals = np.exp(vals / temperature)
    probs = exp_vals / exp_vals.sum()

    return {name: float(prob) for name, prob in zip(names, probs)}


def monte_carlo_tournament(
    golfers: List[GolferProfile],
    n_simulations: int = 50000,
    rounds: int = 4,
    seed: Optional[int] = None,
) -> Dict[str, Dict[str, float]]:
    """Run Monte Carlo tournament simulation.

    Each golfer's round score is sampled from Normal(72 - sg_total, consistency).
    Returns {name: {win: prob, top5: prob, top10: prob, top20: prob, make_cut: prob}}.
    """
    if seed is not None:
        np.random.seed(seed)

    n = len(golfers)
    names = [g.name for g in golfers]

    # Parameters: mean = par - sg_total, std = consistency
    means = np.array([72 - g.sg_total for g in golfers])
    stds = np.array([max(g.consistency, 0.5) for g in golfers])

    # Simulate: shape (n_simulations, n_golfers, rounds)
    scores = np.random.normal(
        means[np.newaxis, :, np.newaxis],
        stds[np.newaxis, :, np.newaxis],
        size=(n_simulations, n, rounds),
    )

    # Total score per golfer per sim
    totals = scores.sum(axis=2)  # (n_simulations, n_golfers)

    # Rank each simulation (lower total = better rank)
    ranks = totals.argsort(axis=1).argsort(axis=1) + 1  # 1-indexed ranks

    results = {}
    for i, name in enumerate(names):
        player_ranks = ranks[:, i]
        results[name] = {
            "win": float((player_ranks == 1).mean()),
            "top5": float((player_ranks <= 5).mean()),
            "top10": float((player_ranks <= 10).mean()),
            "top20": float((player_ranks <= 20).mean()),
            "make_cut": float((player_ranks <= n * 0.55).mean()),  # ~top 55% make cut
            "avg_finish": float(player_ranks.mean()),
        }

    return results


def _load_seed_stats() -> Dict[str, Dict]:
    """Load strokes gained seed data from CSV if available."""
    import os, csv
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "seeds", "masters_strokes_gained.csv")
    if not os.path.exists(csv_path):
        return {}
    stats = {}
    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("name", "").strip()
            if name:
                stats[name] = {
                    "sg_total": float(row.get("sg_total", 0)),
                    "sg_off_tee": float(row.get("sg_off_tee", 0)),
                    "sg_approach": float(row.get("sg_approach", 0)),
                    "sg_around_green": float(row.get("sg_around_green", 0)),
                    "sg_putting": float(row.get("sg_putting", 0)),
                    "consistency": float(row.get("consistency", 2.0)),
                }
    return stats


def build_profiles_from_data(
    leaderboard: List[Dict],
    rankings: List[Dict] = None,
    stats: Dict[str, Dict] = None,
    course_history: Dict[str, List[int]] = None,
) -> List[GolferProfile]:
    """Build GolferProfile objects from available data sources.

    Automatically loads seed CSV data if no stats dict is provided.
    """
    # Auto-load seed data if none provided
    if stats is None:
        stats = _load_seed_stats()

    ranking_map = {}
    if rankings:
        for r in rankings:
            ranking_map[r["name"]] = r.get("rank", 200)

    profiles = []
    for entry in leaderboard:
        name = entry.get("name", "")
        if not name:
            continue

        profile = GolferProfile(name=name)
        profile.world_ranking = ranking_map.get(name, 200)

        # Populate stats from seed data or provided stats
        if stats and name in stats:
            s = stats[name]
            profile.sg_total = s.get("sg_total", 0.0)
            profile.sg_tee_to_green = s.get("sg_tee_to_green", 0.0)
            profile.sg_approach = s.get("sg_approach", 0.0)
            profile.sg_putting = s.get("sg_putting", 0.0)
            profile.sg_off_tee = s.get("sg_off_tee", 0.0)
            profile.sg_around_green = s.get("sg_around_green", 0.0)
            profile.consistency = s.get("consistency", 2.0)

        # Course history score: avg of normalized finishes (1st=1.0, 50th≈0.0)
        if course_history and name in course_history:
            finishes = course_history[name]
            if finishes:
                # Convert finishes to 0-1 scores (1st place = best)
                scores = [max(0, 1 - (f - 1) / 49) for f in finishes]
                profile.course_history_score = sum(scores) / len(scores)

        profiles.append(profile)

    return profiles
