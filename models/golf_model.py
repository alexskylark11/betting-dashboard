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
    from pathlib import Path
    import csv

    # Try multiple path resolutions for compatibility across environments
    candidates = [
        Path(__file__).resolve().parent.parent / "data" / "seeds" / "masters_strokes_gained.csv",
        Path.cwd() / "data" / "seeds" / "masters_strokes_gained.csv",
    ]

    csv_path = None
    for c in candidates:
        if c.exists():
            csv_path = c
            break

    if csv_path is None:
        return _fallback_seed_stats()

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
    return stats if stats else _fallback_seed_stats()


def _fallback_seed_stats() -> Dict[str, Dict]:
    """Hardcoded seed data for top players — used when CSV can't be found."""
    raw = {
        "Scottie Scheffler":  (2.50, 0.45, 0.89, 0.52, 0.36, 1.61),
        "Xander Schauffele":  (2.00, 0.42, 0.99, 0.31, 0.42, 1.58),
        "Rory McIlroy":       (1.80, 0.30, 0.82, 0.51, 0.33, 1.57),
        "Jon Rahm":           (1.70, 0.36, 0.41, 0.15, 0.10, 1.74),
        "Collin Morikawa":    (1.60, 0.50, 0.77, 0.38, 0.07, 1.66),
        "Ludvig Aberg":       (1.50, 0.23, 0.74, 0.20, 0.28, 1.98),
        "Viktor Hovland":     (1.40, 0.26, 0.20,-0.08, 0.58, 2.17),
        "Sahith Theegala":    (1.30, 0.56, 0.50, 0.36, 0.33, 1.94),
        "Hideki Matsuyama":   (1.30, 0.32, 0.32, 0.11, 0.34, 1.95),
        "Brooks Koepka":      (1.30, 0.12, 0.47,-0.01, 0.23, 1.93),
        "Patrick Cantlay":    (1.20, 0.18, 0.16, 0.47, 0.27, 1.84),
        "Jordan Spieth":      (1.20, 0.66, 0.38, 0.30, 0.05, 2.02),
        "Wyndham Clark":      (1.20, 0.66, 0.23, 0.29, 0.18, 1.98),
        "Sam Burns":          (1.10, 0.48, 0.19, 0.35, 0.40, 1.84),
        "Shane Lowry":        (1.10, 0.05, 0.17, 0.25, 0.15, 1.90),
        "Justin Thomas":      (1.10, 0.33, 0.40,-0.07, 0.51, 1.94),
        "Tommy Fleetwood":    (1.00, 0.46, 0.21, 0.25, 0.45, 1.99),
        "Tony Finau":         (1.00, 0.26, 0.60, 0.13, 0.49, 1.93),
        "Sungjae Im":         (1.00, 0.48, 0.57, 0.30, 0.23, 2.13),
        "Cameron Smith":      (0.90, 0.29, 0.20, 0.04, 0.07, 1.98),
        "Keegan Bradley":     (0.90, 0.31, 0.41,-0.13, 0.17, 1.98),
        "Tom Kim":            (0.90,-0.02, 0.44, 0.07, 0.15, 2.17),
        "Robert MacIntyre":   (0.85, 0.03, 0.25, 0.00, 0.12, 1.90),
        "Corey Conners":      (0.85, 0.17, 0.42, 0.39,-0.12, 1.99),
        "Min Woo Lee":        (0.80, 0.43, 0.30,-0.10, 0.10, 1.85),
        "Russell Henley":     (0.80, 0.43, 0.22,-0.13, 0.22, 1.93),
        "Sepp Straka":        (0.80, 0.09, 0.21, 0.01, 0.23, 1.88),
        "Denny McCarthy":     (0.75, 0.10, 0.56,-0.07, 0.25, 2.01),
        "Brian Harman":       (0.70, 0.38, 0.02, 0.02,-0.03, 1.92),
        "Matt Fitzpatrick":   (0.70, 0.01, 0.52, 0.24, 0.19, 2.01),
        "Cameron Young":      (0.70, 0.20, 0.16,-0.02, 0.07, 1.96),
        "Tyrrell Hatton":     (0.65, 0.42, 0.48, 0.38, 0.31, 1.89),
        "Chris Kirk":         (0.65, 0.15, 0.12, 0.01,-0.10, 2.09),
        "Jason Day":          (0.65, 0.14,-0.07, 0.01, 0.15, 1.88),
        "Si Woo Kim":         (0.60, 0.19, 0.03, 0.31, 0.31, 2.19),
        "Adam Scott":         (0.60, 0.09, 0.29, 0.19, 0.36, 1.85),
        "Will Zalatoris":     (0.60, 0.29, 0.51, 0.38,-0.10, 1.95),
        "Max Homa":           (0.55,-0.11, 0.22,-0.11, 0.11, 1.86),
        "Billy Horschel":     (0.50, 0.33, 0.03,-0.10, 0.00, 2.42),
        "Byeong Hun An":      (0.50, 0.10, 0.45, 0.12, 0.07, 2.39),
        "Akshay Bhatia":      (0.50, 0.41, 0.17, 0.05,-0.15, 2.43),
        "Dustin Johnson":     (0.50, 0.17,-0.10, 0.16, 0.03, 2.35),
        "Stephan Jaeger":     (0.45,-0.07, 0.20, 0.13, 0.00, 2.32),
        "Eric Cole":          (0.45,-0.03, 0.35, 0.06, 0.18, 2.35),
        "Nick Dunlap":        (0.45,-0.13, 0.24, 0.17,-0.12, 2.44),
        "Taylor Moore":       (0.40,-0.05,-0.13, 0.04, 0.22, 2.49),
        "Joaquin Niemann":    (0.35, 0.14,-0.15, 0.19,-0.07, 2.38),
        "Sergio Garcia":      (0.30, 0.01, 0.03, 0.25, 0.27, 2.47),
        "Patrick Reed":       (0.25, 0.24, 0.27, 0.32, 0.01, 2.23),
        "Tiger Woods":        (0.20,-0.23, 0.05, 0.11, 0.27, 2.30),
        "Phil Mickelson":     (0.10, 0.26, 0.31,-0.01, 0.01, 2.47),
        "Danny Willett":      (0.10, 0.00, 0.32, 0.30,-0.04, 2.30),
        "Bubba Watson":       (0.05,-0.27,-0.26, 0.00, 0.04, 2.32),
        "Zach Johnson":       (0.00, 0.03, 0.10, 0.05, 0.07, 2.56),
        "Fred Couples":       (-0.50, 0.14, 0.00,-0.15,-0.22, 2.54),
        "Jose Maria Olazabal":(-0.80,-0.45,-0.29,-0.39,-0.28, 2.63),
        "Vijay Singh":        (-1.00,-0.04,-0.27, 0.10,-0.05, 2.93),
        "Larry Mize":         (-1.20,-0.40,-0.28,-0.05,-0.39, 2.71),
        "Sandy Lyle":         (-1.50,-0.28,-0.45,-0.23,-0.12, 2.91),
    }
    stats = {}
    for name, (sg_t, sg_ot, sg_a, sg_ag, sg_p, con) in raw.items():
        stats[name] = {
            "sg_total": sg_t, "sg_off_tee": sg_ot, "sg_approach": sg_a,
            "sg_around_green": sg_ag, "sg_putting": sg_p, "consistency": con,
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
