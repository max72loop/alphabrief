"""Score EN OMBRE — calculé et historisé à chaque scoring, jamais affiché.

Le score de prod ne trie pas les rendements (backtest du 22/09 : écart bande
haute − bande basse −0,33 pt, « Exceptionnel » −0,54 % sur 68 observations). Ce
module prépare son remplaçant sans rien changer à ce que voit Max : il tourne à
côté, s'écrit dans `scores_history.ombre_json`, et le backtest mensuel dira
s'il trie mieux (corrélation de rang, `scripts/backtest.py`).

Deux différences de méthode avec `potential.py` :

1. **Une métrique par idée**, pas sept. Rentabilité = ROA, valorisation =
   rendement bénéficiaire (1 / P/E forward, repli TTM), croissance = CAGR du
   chiffre d'affaires sur 3 ans, solidité = dette nette / EBITDA. Le moteur de
   prod compte la même idée plusieurs fois (EBIT, marge nette, marge FCF, ROE,
   ROA… ; P/E, forward P/E, PEG, EV/EBITDA, EV/Sales, P/OCF, FCF yield).

2. **Percentile dans le secteur**, pas des fourchettes écrites à la main. Chaque
   métrique est classée contre la distribution de son secteur dans un
   échantillon du S&P 500 (`data/ombre_reference.json`, construit par
   `scripts/reference_ombre.py`). Un ROA de 2 % est médiocre pour un éditeur de
   logiciels et bon pour une banque : le percentile le dit, une borne fixe non.

Côté prix, on garde la valeur brute du momentum 12-1 relatif au secteur (12 mois
sans le dernier, moins l'ETF du secteur sur la même fenêtre) : le backtest la
classe lui-même, un percentile sur ~40 titres de watchlist n'ajouterait rien.
"""

from __future__ import annotations

import bisect
import json
from pathlib import Path
from typing import Any, Dict, Optional

VERSION = "ombre-1"
REFERENCE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "ombre_reference.json"

# Sous ce nombre de sociétés, la distribution d'un secteur ne dit rien : on
# classe alors contre l'échantillon entier.
MIN_PAR_SECTEUR = 8

# nom → sens (+1 : plus haut = mieux, −1 : plus bas = mieux)
METRIQUES = {
    "rentabilite": +1,
    "valorisation": +1,
    "croissance": +1,
    "solidite": -1,
}

_reference: Optional[Dict[str, Dict[str, list]]] = None


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def metriques(card: Dict[str, Any]) -> Dict[str, Optional[float]]:
    """Les quatre valeurs brutes d'une carte (None si absentes)."""
    fin = card.get("financials", {}) or {}
    val = card.get("valuation", {}) or {}
    pe = _num(val.get("forward_pe")) or _num(val.get("pe_ttm"))
    return {
        "rentabilite": _num(fin.get("roa")),
        # 1/PE garde son signe : une perte classe la société en bas, ce qu'un
        # P/E négatif « attractif » ne ferait pas.
        "valorisation": (1.0 / pe) if pe else None,
        "croissance": _num(fin.get("revenue_cagr_3y")),
        "solidite": _num(fin.get("net_debt_to_ebitda")),
    }


def charger_reference(path: Path = REFERENCE_PATH) -> Dict[str, Dict[str, list]]:
    global _reference
    if _reference is None:
        try:
            _reference = json.loads(path.read_text(encoding="utf-8"))["secteurs"]
        except (OSError, ValueError, KeyError):
            _reference = {}
    return _reference


def percentile(valeur: float, distribution: list, sens: int) -> float:
    """Rang 0-100 de `valeur` dans `distribution` (triée), rangs moyens aux ex æquo."""
    bas = bisect.bisect_left(distribution, valeur)
    haut = bisect.bisect_right(distribution, valeur)
    p = 100.0 * (bas + haut) / 2.0 / len(distribution)
    return p if sens > 0 else 100.0 - p


def momentum_12_1_relatif(market: Dict[str, Any]) -> Optional[float]:
    """12 mois sans le dernier, en excès de l'ETF du secteur, en %.

    Reconstruit depuis les champs que le moteur a déjà : le titre sur 12 mois et
    1 mois, et les mêmes horizons en relatif (titre − ETF), d'où l'ETF.
    """
    m12, m1 = _num(market.get("momentum_12m")), _num(market.get("momentum_1m"))
    r12, r1 = _num(market.get("relative_momentum_12m")), _num(market.get("relative_momentum_1m"))
    if None in (m12, m1, r12, r1):
        return None
    titre = (1 + m12 / 100) / (1 + m1 / 100) - 1
    etf = (1 + (m12 - r12) / 100) / (1 + (m1 - r1) / 100) - 1
    return round((titre - etf) * 100, 2)


def score_ombre(card: Dict[str, Any], reference: Optional[Dict[str, Dict[str, list]]] = None) -> Dict[str, Any]:
    ref = charger_reference() if reference is None else reference
    identity = card.get("identity", {}) or {}
    secteur = identity.get("sector_note") or identity.get("sector") or ""
    detail: Dict[str, Optional[float]] = {}
    for nom, valeur in metriques(card).items():
        dist = (ref.get(secteur, {}) or {}).get(nom) or []
        if len(dist) < MIN_PAR_SECTEUR:
            dist = (ref.get("_tous", {}) or {}).get(nom) or []
        detail[nom] = (round(percentile(valeur, dist, METRIQUES[nom]), 1)
                       if valeur is not None and dist else None)
    presentes = [v for v in detail.values() if v is not None]
    return {
        "version": VERSION,
        # Moins de deux métriques : pas de verdict, plutôt qu'un chiffre bâti sur une seule.
        "fondamentaux": round(sum(presentes) / len(presentes), 1) if len(presentes) >= 2 else None,
        "detail": detail,
        "m121_rel": momentum_12_1_relatif(card.get("market", {}) or {}),
        # Prime de rendement contre le 10 ans (2026-10-27) — EN OMBRE par décision
        # de Max : historisée ici pour que le backtest mesure son pouvoir de tri
        # avant qu'elle ne pèse quoi que ce soit. Sa version voyage avec elle
        # (`prime-N`), celle de l'ombre ne change pas : la série `fondamentaux`
        # reste comparable d'un jour à l'autre.
        "prime": _prime(card.get("rendement") or {}),
    }


def _prime(r: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not r:
        return None
    return {k: r.get(k) for k in ("version", "prime", "flag", "base", "rendement", "taux_10y", "prime_ey")}
