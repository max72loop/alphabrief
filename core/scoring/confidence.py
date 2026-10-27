"""Couverture des données d'une carte — « qu'est-ce qu'on sait de cette société ».

Ce n'est PAS un jugement sur la société : c'est la part des entrées du moteur
qui sont réellement renseignées. Les deux ont longtemps été mélangés dans un
seul nombre, `core/generator.py` rabotant la note de 0 à 20 % selon cette
couverture. Le rabot est retiré : la note dit la qualité, la confiance dit ce
qu'on ignore, et c'est la confiance qui décide si la carte a le droit d'afficher
un verdict (`core.scoring.bands.CONFIDENCE_FLOOR`).

Cette liste doit donc rester le miroir exact de ce que lit
`compute_potential_score`. Elle avait dérivé : ~17 entrées ajoutées au moteur au
fil des améliorations n'y figuraient pas, si bien qu'une carte pouvait annoncer
« confiance 96 » en ignorant un tiers de ce que le moteur lisait vraiment.
`tests/core/scoring/test_confidence_couvre_le_moteur.py` échoue désormais si
l'écart se recreuse.
"""

from typing import Any, Dict

# Champs lus par le moteur mais qui ne sont pas des VALEURS notées : ils
# choisissent le barème sectoriel à appliquer. Leur absence dégrade la
# calibration, pas la couverture — le moteur retombe sur `_DEFAULT_*_RANGE`.
CALIBRATION_ONLY = {("identity", "sector"), ("identity", "sector_note"), ("identity", "industry")}

# Features pondérées: (section, key, weight)
#
# Le poids reflète la contribution réelle de la métrique au score final, donc la
# pondération des piliers (fondamentaux 50 %, technique 25 %, momentum 25 %) et
# celle des composants à l'intérieur de chaque pilier. L'ancienne liste pesait
# lourdement la valorisation et ne comptait presque pas le momentum ni la
# technique — la moitié du score.
FEATURES = [
    # ── Fondamentaux · Valeur (le pilier le plus lourd : ~16 % du total) ──
    ("valuation", "fcf_yield_ttm", 1.6),
    ("valuation", "ev_ebitda_ttm", 1.4),
    ("valuation", "peg_ratio", 1.4),
    ("valuation", "pe_ttm", 1.3),
    ("valuation", "forward_pe", 1.3),
    ("valuation", "price_to_ocf", 1.0),
    ("valuation", "pb_ratio", 0.9),
    ("valuation", "ev_sales_ttm", 0.8),
    ("market", "dividend_yield", 1.0),
    ("financials", "payout_ratio", 0.5),
    # ── Fondamentaux · Qualité (~11,5 % du total) ──
    ("financials", "ebit_margin", 1.2),
    ("financials", "fcf_margin", 0.9),
    ("financials", "gross_margin", 0.7),
    ("financials", "roe", 0.7),
    ("financials", "roa", 0.7),
    ("financials", "net_margin", 0.6),
    # Dilution (2026-10-27) : le moteur lit `dilution_an`, et retombe sur
    # `share_dilution_3y` sans lui. Le poids d'origine (0,6) est partagé, pour
    # ne pas déplacer les confiances existantes.
    ("financials", "dilution_an", 0.3),
    ("financials", "share_dilution_3y", 0.3),
    ("financials", "gross_margin_trend", 0.6),
    ("financials", "accruals_ratio", 0.6),
    ("financials", "fcf_absolute", 0.5),
    ("financials", "net_income", 0.5),
    ("financials", "insider_ownership", 0.5),
    ("financials", "institutional_ownership", 0.5),
    # ── Fondamentaux · Croissance (~8,5 % du total) ──
    ("financials", "revenue_cagr_3y", 1.3),
    ("financials", "revenue_yoy_rates", 1.0),
    ("financials", "eps_growth", 0.9),
    # ── Fondamentaux · Risque (~6,5 % du total) ──
    ("financials", "net_debt_to_ebitda", 1.0),
    ("market", "beta", 0.8),
    ("financials", "interest_coverage", 0.8),
    ("financials", "altman_z", 0.7),
    ("financials", "current_ratio", 0.6),
    ("financials", "short_interest", 0.5),
    # ── Fondamentaux · Consensus analystes (~7,5 % du total) ──
    ("market", "analyst_target_mean", 1.5),
    ("market", "analyst_recommendation", 1.0),
    ("market", "analyst_count", 0.5),
    # ── Momentum (25 % du total) ──
    ("market", "momentum_12m", 1.6),
    ("market", "momentum_6m", 1.2),
    ("market", "relative_momentum_12m", 1.2),
    ("market", "momentum_3m", 0.8),
    ("market", "relative_momentum_3m", 0.7),
    ("market", "relative_momentum_1m", 0.5),
    ("market", "momentum_1m", 0.4),
    ("technicals", "volatility_1y", 0.8),
    # ── Technique (25 % du total) ──
    ("technicals", "rsi_14", 1.5),
    ("market", "current_price", 1.0),
    ("technicals", "sma_200", 0.9),
    ("technicals", "sma_50", 0.9),
    ("technicals", "macd_line", 0.8),
    ("market", "fifty_two_week_low", 0.7),
    ("market", "fifty_two_week_high", 0.7),
    ("technicals", "max_drawdown_1y", 0.6),
    ("technicals", "macd_signal", 0.5),
    ("technicals", "macd_histogram", 0.5),
]


def compute_confidence_score(card: Dict[str, Any]) -> int:
    """
    Score de confiance 0-100 basé sur la disponibilité des données.
    Pondéré par l'importance de chaque métrique pour le score final.
    """
    total_weight = sum(w for _, _, w in FEATURES)
    available_weight = 0.0

    for section, key, weight in FEATURES:
        if card.get(section, {}).get(key) is not None:
            available_weight += weight

    return int(round(100 * available_weight / total_weight))
