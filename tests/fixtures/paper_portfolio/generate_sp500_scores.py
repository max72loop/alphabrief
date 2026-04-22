"""Deterministic generator for mock_fmp_scores_sp500.json (seed=42).

Convention : raw_components.
    Chaque composante score_breakdown ∈ [0, 100] (score brut par pilier).
    score total = round(0.5 * fundamentals + 0.25 * technicals + 0.25 * momentum)

Lit data/sp500_tickers.csv (500 tickers, sector, tier).
Génère un target_score ~ Normal(50, 18) clampé [0, 100], force 20 extrêmes haut/bas
pour assurer la testabilité TOP10/BOTTOM10, puis décompose en composantes raw
avec jitter préservant la somme pondérée (d_fund, d_tech, d_mom tel que
0.5*d_fund + 0.25*d_tech + 0.25*d_mom = 0, avant clipping).

Invariant post-génération (testable) :
    abs(score - (0.5*fund + 0.25*tech + 0.25*mom)) <= 0.5  ∀ entrée
    (écart ≤ 0.5 dû au rounding des composantes en entiers)

Fichier produit byte-identique à chaque run.

Usage: python tests/fixtures/paper_portfolio/generate_sp500_scores.py
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np

SEED = 42
MEAN = 50
STD = 18
SCORE_DATE = "2026-04-17"
GENERATED_AT = "2026-04-17T22:00:00Z"

WEIGHT_FUND = 0.50
WEIGHT_TECH = 0.25
WEIGHT_MOM = 0.25

ROOT = Path(__file__).parent
CSV_PATH = ROOT / "data" / "sp500_tickers.csv"
OUTPUT_PATH = ROOT / "mock_fmp_scores_sp500.json"

TIER_MARKET_CAP = {
    "mega": (500_000_000_000, 3_500_000_000_000),
    "large": (100_000_000_000, 500_000_000_000),
    "mid": (30_000_000_000, 100_000_000_000),
    "small": (1_000_000_000, 30_000_000_000),
}
TIER_PRICE = {
    "mega": (80, 800),
    "large": (40, 500),
    "mid": (15, 250),
    "small": (3, 120),
}


def _decompose_raw(target: float, rng) -> tuple[int, int, int]:
    """Décompose un score cible en composantes raw [0,100] avec jitter à somme pondérée nulle.

    0.5*d_fund + 0.25*d_tech + 0.25*d_mom = 0  (invariant avant clipping).
    Jitter choisi : d_fund, d_tech libres ; d_mom = -2*d_fund - d_tech.
    """
    d_fund = float(rng.uniform(-8, 8))
    d_tech = float(rng.uniform(-12, 12))
    d_mom = -2 * d_fund - d_tech
    fund = int(round(max(0.0, min(100.0, target + d_fund))))
    tech = int(round(max(0.0, min(100.0, target + d_tech))))
    mom = int(round(max(0.0, min(100.0, target + d_mom))))
    return fund, tech, mom


def _load_universe() -> list[tuple[str, str, str]]:
    with open(CSV_PATH, newline="") as f:
        reader = csv.reader(f)
        next(reader)
        return [(r[0], r[1], r[2]) for r in reader]


def generate_scores() -> dict:
    universe = _load_universe()
    n = len(universe)
    rng = np.random.default_rng(SEED)

    target = np.clip(rng.normal(MEAN, STD, n), 0, 100)
    sorted_idx = np.argsort(target)
    target[sorted_idx[-20:]] = rng.integers(80, 96, 20)
    target[sorted_idx[:20]] = rng.integers(5, 31, 20)

    fund_arr, tech_arr, mom_arr = np.zeros(n, int), np.zeros(n, int), np.zeros(n, int)
    for i in range(n):
        fund_arr[i], tech_arr[i], mom_arr[i] = _decompose_raw(float(target[i]), rng)

    score_arr = np.round(
        WEIGHT_FUND * fund_arr + WEIGHT_TECH * tech_arr + WEIGHT_MOM * mom_arr
    ).astype(int)

    market_caps, prices = np.empty(n, dtype=np.int64), np.empty(n)
    for i, (_, _, tier) in enumerate(universe):
        mc_lo, mc_hi = TIER_MARKET_CAP[tier]
        market_caps[i] = int(np.exp(rng.uniform(np.log(mc_lo), np.log(mc_hi))))
        p_lo, p_hi = TIER_PRICE[tier]
        prices[i] = round(rng.uniform(p_lo, p_hi), 2)

    scores = [
        {
            "ticker": ticker,
            "score": int(score_arr[i]),
            "score_breakdown": {
                "fundamentals": int(fund_arr[i]),
                "technicals": int(tech_arr[i]),
                "momentum": int(mom_arr[i]),
            },
            "price_friday_close": float(prices[i]),
            "sector": sector,
            "market_cap": int(market_caps[i]),
            "score_date": SCORE_DATE,
        }
        for i, (ticker, sector, _tier) in enumerate(universe)
    ]

    # Vérification de l'invariant de convention
    max_dev = 0.0
    for s in scores:
        b = s["score_breakdown"]
        computed = WEIGHT_FUND * b["fundamentals"] + WEIGHT_TECH * b["technicals"] + WEIGHT_MOM * b["momentum"]
        dev = abs(s["score"] - computed)
        if dev > max_dev:
            max_dev = dev

    stats = {
        "min": int(score_arr.min()),
        "max": int(score_arr.max()),
        "median": float(np.median(score_arr)),
        "p10": float(np.percentile(score_arr, 10)),
        "p90": float(np.percentile(score_arr, 90)),
        "count_ge_80": int((score_arr >= 80).sum()),
        "count_le_30": int((score_arr <= 30).sum()),
        "max_convention_deviation": float(max_dev),
    }

    return {
        "fixture_name": "mock_fmp_scores_sp500",
        "generated_at": GENERATED_AT,
        "seed": SEED,
        "score_date": SCORE_DATE,
        "universe_size": n,
        "meta": {
            "score_convention": "raw_components",
            "description": (
                "score_breakdown.{fundamentals,technicals,momentum} are raw scores "
                "each in [0,100]. Total score = round(0.50*fund + 0.25*tech + 0.25*mom). "
                "Invariant: abs(score - weighted_sum) <= 0.5 due to independent integer "
                "rounding of components."
            ),
            "weights": {
                "fundamentals": WEIGHT_FUND,
                "technicals": WEIGHT_TECH,
                "momentum": WEIGHT_MOM,
            },
            "component_range": [0, 100],
            "target_distribution": f"Normal(mean={MEAN}, std={STD}) clipped to [0,100]",
            "forced_extremes": "20 top (target in [80,95]) + 20 bottom (target in [5,30])",
        },
        "stats": stats,
        "scores": scores,
    }


if __name__ == "__main__":
    data = generate_scores()
    OUTPUT_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    s = data["stats"]
    print(f"Wrote {OUTPUT_PATH}")
    print(f"  universe_size={data['universe_size']}  convention={data['meta']['score_convention']}")
    print(f"  min={s['min']}  p10={s['p10']}  median={s['median']}  p90={s['p90']}  max={s['max']}")
    print(f"  count_ge_80={s['count_ge_80']}  count_le_30={s['count_le_30']}")
    print(f"  max_convention_deviation={s['max_convention_deviation']}  (expected <= 0.5)")
