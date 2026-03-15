"""
Seuils de scoring adaptatifs par secteur.

Chaque secteur a des caractéristiques différentes:
- Technology: P/E élevés acceptables, forte croissance attendue
- Utilities: P/E bas, marges stables, dividendes
- Financial Services: P/B plus pertinent, ROE crucial
- Healthcare: P/E très variables (biotech vs pharma établie)
- Consumer Defensive: Marges stables, croissance modérée
- Energy: Cyclique, FCF yield important
- Industrials: P/E moyens, croissance liée au cycle économique
"""

from typing import Dict, Any

# Structure: {metric: (lo, hi)} pour score_linear
# Pour les métriques inverses (P/E, EV/EBITDA), lo = bon, hi = mauvais
SECTOR_THRESHOLDS: Dict[str, Dict[str, tuple]] = {
    "Technology": {
        "pe": (15.0, 50.0),           # Tech peut avoir des P/E plus élevés
        "ev_ebitda": (10.0, 30.0),    # EV/EBITDA plus tolérant
        "ebit_margin": (10.0, 35.0),  # Marges potentiellement très élevées
        "roe": (10.0, 30.0),          # ROE élevé attendu
        "revenue_cagr": (5.0, 30.0),  # Forte croissance attendue
        "fcf_yield": (1.0, 6.0),      # FCF yield plus bas acceptable
    },
    "Financial Services": {
        "pe": (8.0, 20.0),            # P/E généralement plus bas
        "ev_ebitda": (5.0, 15.0),     # Moins pertinent pour finance
        "ebit_margin": (15.0, 40.0),  # Marges peuvent être très élevées
        "roe": (8.0, 20.0),           # ROE crucial pour les banques
        "revenue_cagr": (0.0, 15.0),  # Croissance plus modérée
        "fcf_yield": (2.0, 10.0),     # FCF yield important
    },
    "Healthcare": {
        "pe": (12.0, 45.0),           # Variable (pharma vs biotech)
        "ev_ebitda": (8.0, 25.0),
        "ebit_margin": (5.0, 30.0),   # Très variable
        "roe": (5.0, 25.0),
        "revenue_cagr": (0.0, 20.0),
        "fcf_yield": (1.0, 7.0),
    },
    "Consumer Cyclical": {
        "pe": (10.0, 30.0),
        "ev_ebitda": (6.0, 18.0),
        "ebit_margin": (5.0, 20.0),
        "roe": (8.0, 25.0),
        "revenue_cagr": (0.0, 20.0),
        "fcf_yield": (2.0, 8.0),
    },
    "Consumer Defensive": {
        "pe": (12.0, 28.0),           # Valorisations stables
        "ev_ebitda": (8.0, 18.0),
        "ebit_margin": (8.0, 25.0),   # Marges stables
        "roe": (10.0, 25.0),
        "revenue_cagr": (0.0, 12.0),  # Croissance modérée
        "fcf_yield": (3.0, 8.0),
    },
    "Energy": {
        "pe": (6.0, 20.0),            # P/E généralement bas
        "ev_ebitda": (4.0, 12.0),     # EV/EBITDA bas
        "ebit_margin": (5.0, 25.0),   # Cyclique
        "roe": (5.0, 20.0),
        "revenue_cagr": (-5.0, 15.0), # Peut être négatif (cyclique)
        "fcf_yield": (4.0, 12.0),     # FCF yield élevé attendu
    },
    "Utilities": {
        "pe": (10.0, 22.0),           # P/E bas et stables
        "ev_ebitda": (6.0, 14.0),
        "ebit_margin": (15.0, 35.0),  # Marges régulées mais stables
        "roe": (6.0, 15.0),           # ROE plus modeste
        "revenue_cagr": (0.0, 8.0),   # Croissance lente
        "fcf_yield": (3.0, 8.0),
    },
    "Industrials": {
        "pe": (10.0, 28.0),
        "ev_ebitda": (6.0, 18.0),
        "ebit_margin": (5.0, 20.0),
        "roe": (8.0, 22.0),
        "revenue_cagr": (0.0, 15.0),
        "fcf_yield": (2.0, 8.0),
    },
    "Basic Materials": {
        "pe": (8.0, 22.0),            # Cyclique
        "ev_ebitda": (5.0, 14.0),
        "ebit_margin": (5.0, 25.0),
        "roe": (5.0, 20.0),
        "revenue_cagr": (-5.0, 15.0), # Cyclique
        "fcf_yield": (3.0, 10.0),
    },
    "Real Estate": {
        "pe": (15.0, 40.0),           # P/E moins pertinent (utiliser P/FFO)
        "ev_ebitda": (10.0, 25.0),
        "ebit_margin": (20.0, 50.0),  # Marges élevées typiques
        "roe": (3.0, 15.0),           # ROE souvent plus bas
        "revenue_cagr": (0.0, 12.0),
        "fcf_yield": (3.0, 8.0),
    },
    "Communication Services": {
        "pe": (12.0, 35.0),
        "ev_ebitda": (6.0, 20.0),
        "ebit_margin": (10.0, 30.0),
        "roe": (8.0, 25.0),
        "revenue_cagr": (0.0, 20.0),
        "fcf_yield": (2.0, 8.0),
    },
}

# Seuils par défaut (utilisés si secteur inconnu)
DEFAULT_THRESHOLDS = {
    "pe": (10.0, 40.0),
    "ev_ebitda": (8.0, 25.0),
    "ebit_margin": (5.0, 30.0),
    "roe": (5.0, 25.0),
    "revenue_cagr": (0.0, 25.0),
    "fcf_yield": (1.0, 8.0),
}


def get_sector_thresholds(sector: str) -> Dict[str, tuple]:
    """
    Retourne les seuils pour un secteur donné.
    Utilise les seuils par défaut si le secteur est inconnu.
    """
    if not sector:
        return DEFAULT_THRESHOLDS
    return SECTOR_THRESHOLDS.get(sector, DEFAULT_THRESHOLDS)


def normalize_sector(sector: str) -> str:
    """
    Normalise le nom du secteur pour correspondre aux clés du dictionnaire.
    """
    if not sector:
        return ""

    # Mapping des variations courantes
    sector_mapping = {
        "technology": "Technology",
        "tech": "Technology",
        "financial": "Financial Services",
        "financials": "Financial Services",
        "finance": "Financial Services",
        "healthcare": "Healthcare",
        "health care": "Healthcare",
        "consumer cyclical": "Consumer Cyclical",
        "consumer discretionary": "Consumer Cyclical",
        "consumer defensive": "Consumer Defensive",
        "consumer staples": "Consumer Defensive",
        "energy": "Energy",
        "utilities": "Utilities",
        "industrials": "Industrials",
        "industrial": "Industrials",
        "basic materials": "Basic Materials",
        "materials": "Basic Materials",
        "real estate": "Real Estate",
        "communication services": "Communication Services",
        "communication": "Communication Services",
        "telecom": "Communication Services",
    }

    sector_lower = sector.lower().strip()
    return sector_mapping.get(sector_lower, sector)
