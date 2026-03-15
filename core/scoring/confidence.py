from typing import Dict, Any

# Features pondérées: (section, key, weight)
# Weight reflète l'importance de la métrique pour le score
FEATURES = [
    # Quality metrics
    ("financials", "ebit_margin", 1.5),
    ("financials", "gross_margin", 1.0),
    ("financials", "roe", 1.0),
    ("financials", "fcf_margin", 1.0),
    ("financials", "fcf_absolute", 0.5),
    ("financials", "net_income", 0.5),
    ("financials", "share_dilution_3y", 0.8),
    # Growth metrics
    ("financials", "revenue_cagr_3y", 1.5),
    ("financials", "revenue_yoy_rates", 1.0),
    # Value metrics (les plus importantes)
    ("valuation", "fcf_yield_ttm", 1.5),
    ("valuation", "pe_ttm", 2.0),
    ("valuation", "forward_pe", 1.5),
    ("valuation", "peg_ratio", 1.2),
    ("valuation", "ev_ebitda_ttm", 1.5),
    ("valuation", "ev_sales_ttm", 0.8),
    ("valuation", "pb_ratio", 1.0),
    ("financials", "payout_ratio", 0.5),
    # Market metrics
    ("market", "momentum_12m", 1.0),
    ("market", "beta", 1.0),
    ("market", "dividend_yield", 1.0),
    # Technical metrics
    ("technicals", "rsi_14", 1.0),
    ("technicals", "sma_200", 0.5),
    ("technicals", "macd_histogram", 0.5),
    ("market", "fifty_two_week_low", 0.5),
    ("market", "fifty_two_week_high", 0.5),
    ("technicals", "volatility_1y", 0.8),
    ("technicals", "max_drawdown_1y", 0.5),
    # Risk metrics
    ("financials", "net_debt_to_ebitda", 1.5),
    ("financials", "interest_coverage", 1.0),
    # Analyst consensus
    ("market", "analyst_target_mean", 1.5),
    ("market", "analyst_count", 0.5),
    ("market", "analyst_recommendation", 1.0),
]


def compute_confidence_score(card: Dict[str, Any]) -> int:
    """
    Score de confiance 0-100 basé sur la disponibilité des données.
    Pondéré par l'importance de chaque métrique.
    """
    total_weight = sum(w for _, _, w in FEATURES)
    available_weight = 0.0

    for section, key, weight in FEATURES:
        if card.get(section, {}).get(key) is not None:
            available_weight += weight

    return int(round(100 * available_weight / total_weight))
