"""Dilution des actionnaires sur 1 an et 3 ans, en % PAR AN (2026-10-27).

Remplace la lecture « total sur 3 exercices » de `share_dilution_3y`, qui ne
distinguait pas une société qui dilue de 6 %/an depuis un an (néocloud qui se
finance en actions) d'une autre qui a dilué une fois il y a trois ans.

Source : nombre d'actions DILUÉES moyen, trimestriel (FMP `income-statement`
period=quarter, `weightedAverageShsOutDil`), du plus récent au plus ancien :
  · 1 an  = T0 contre T−4 ;
  · 3 ans = T0 contre T−12, annualisé ((T0/T−12)^(1/3) − 1).

Événement sur le capital : une CHUTE de plus de SAUT_EVENEMENT d'un trimestre
à l'autre dans la fenêtre (sortie d'un actionnaire, regroupement — NBIS passe
de 372 M à 240 M d'actions en 2024 avec la sortie de Yandex). La fenêtre reste
AFFICHÉE mais n'entre pas dans la note : un rachat ponctuel de cette taille
n'est pas une politique de rachat. Une HAUSSE brutale, elle, compte toujours :
c'est exactement la dilution qu'on veut voir (IREN, +41 %/an).

Introduction en bourse : avant elle, le nombre moyen d'actions mélange les
actions de préférence converties et le flottant — CRCL passe de 73 M à 269 M
autour de son IPO sans qu'aucun actionnaire public n'ait été dilué. Une
fenêtre qui commence avant le premier trimestre complet coté (IPO + 90 j)
n'est pas calculée.

Note : on retient la PIRE des deux fenêtres propres. La dilution récente est
celle qui coûte (un néocloud qui se met à diluer ne doit pas être blanchi par
trois ans de calme), et un « rachat net » doit tenir sur les deux horizons.

Pur : aucune E/S.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Dict, List, Optional

VERSION = "dilution-2"

SAUT_EVENEMENT = 0.25   # chute trimestrielle > 25 % → événement sur le capital
DELAI_IPO = timedelta(days=90)


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and v > 0 else None


def _num_signe(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def annualiser(total_pct: Optional[float], annees: float) -> Optional[float]:
    """Une variation totale sur `annees` ans (en %) ramenée en %/an."""
    if total_pct is None or annees <= 0 or total_pct <= -100:
        return None
    return ((1 + total_pct / 100.0) ** (1.0 / annees) - 1.0) * 100.0


def _fenetre(serie: List[Optional[float]], n: int) -> tuple[Optional[float], bool]:
    """Variation %/an entre T0 et T−n, et présence d'une chute brutale dans la fenêtre.

    `serie` va du plus récent au plus ancien : (a, b) = (trimestre, précédent).
    """
    if len(serie) <= n or serie[0] is None or serie[n] is None:
        return None, False
    pts = [s for s in serie[: n + 1] if s is not None]
    evenement = any(a / b - 1.0 < -SAUT_EVENEMENT for a, b in zip(pts, pts[1:]))
    total = (serie[0] / serie[n] - 1.0) * 100.0
    return annualiser(total, n / 4.0), evenement


def _avant_ipo(dates: Optional[List[Any]], n: int, ipo_date: Any) -> bool:
    """La fenêtre T0 → T−n commence-t-elle avant le premier trimestre complet coté ?"""
    if not dates or not ipo_date or len(dates) <= n or not dates[n]:
        return False
    try:
        debut = date.fromisoformat(str(dates[n])[:10])
        ipo = date.fromisoformat(str(ipo_date)[:10])
    except ValueError:
        return False
    return debut < ipo + DELAI_IPO


def calculer_dilution(actions_trimestrielles: List[Any], dilution_3y_annuelle_total: Any = None,
                      dates: Optional[List[Any]] = None, ipo_date: Any = None) -> Dict[str, Any]:
    """`actions_trimestrielles` : actions diluées moyennes, du plus récent au plus ancien.

    `dates` : date de clôture de chaque trimestre (même ordre), `ipo_date` : date
    d'introduction — ensemble, ils écartent les fenêtres d'avant la cotation.
    `dilution_3y_annuelle_total` : repli quand la série trimestrielle manque — la
    variation TOTALE sur 3 exercices déjà calculée depuis les comptes annuels
    (`share_dilution_3y`, yfinance), annualisée ici.
    """
    serie = [_num(x) for x in (actions_trimestrielles or [])]
    d1, ev1 = _fenetre(serie, 4)
    d3, ev3 = _fenetre(serie, 12)
    pre1, pre3 = _avant_ipo(dates, 4, ipo_date), _avant_ipo(dates, 12, ipo_date)
    if pre1:
        d1, ev1 = None, False
    if pre3:
        d3, ev3 = None, False
    source = "trimestriel" if (d1 is not None or d3 is not None) else None
    if d3 is None and not pre3:
        repli = annualiser(_num_signe(dilution_3y_annuelle_total), 3)
        if repli is not None:
            d3, ev3, source = repli, False, source or "annuel"

    propres = [d for d, ev in ((d1, ev1), (d3, ev3)) if d is not None and not ev]
    retenue = max(propres) if propres else None
    return {
        "version": VERSION,
        "dilution_1y": round(d1, 2) if d1 is not None else None,
        "dilution_3y": round(d3, 2) if d3 is not None else None,
        "evenement_1y": ev1,
        "evenement_3y": ev3,
        # Fenêtre écartée parce qu'elle commence avant la cotation (IPO + 90 j).
        "avant_ipo_1y": pre1,
        "avant_ipo_3y": pre3,
        "retenue": round(retenue, 2) if retenue is not None else None,
        "source": source,
    }
