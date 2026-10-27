"""Prime de rendement contre le taux sans risque (2026-10-27).

Une valorisation basse ne suffit plus quand le 10 ans US paie 4 à 5 % sans
risque : une action doit rendre PLUS que l'obligation pour mériter le risque.
Ce module compare donc le rendement de la société au taux 10 ans :

    prime = rendement − taux 10 ans                       (en points)

Le rendement retenu :
  · cas général             : FCF yield TTM ;
  · société en croissance   : FCF yield + croissance du CA attendue (consensus),
    plafonnée à CROISSANCE_PLAFOND — c'est le rendement implicite d'un modèle de
    Gordon simplifié ; sans plafond, 60 % de croissance rendraient « vert »
    n'importe quel multiple ;
  · banque ou assureur      : earnings yield seul (le FCF d'un bilan qui est
    l'outil de production ne mesure rien — même neutralisation que
    `potential.py` ; pas de croissance ajoutée, elle est financée par les
    bénéfices non distribués et serait comptée deux fois).

FCF TTM négatif, nul ou inconnu → état « n/a » (gris), jamais de rouge
automatique : un néocloud qui brûle du cash pour construire ses centres de
données n'est pas « cher », il n'a pas encore de rendement à comparer.
L'earnings yield forward reste alors affiché en information, avec sa propre
prime, sans flag.

Pur : aucune E/S. Le taux et le consensus arrivent dans la carte, posés par
`core.providers.rendement`. Le flag vit EN OMBRE (decision du 2026-10-27) :
affiché, historisé dans `scores_history.ombre_json`, il ne pèse PAS dans la
note tant que son pouvoir de tri n'a pas été mesuré (règle du 2026-09-28 : un
signal sans IC positif à t ≥ 2 ne mérite aucun poids).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

VERSION = "prime-1"

SEUIL_VERT = 2.0            # prime ≥ +2 pts : nettement au-dessus du sans-risque
SEUIL_ROUGE = -1.0          # prime < −1 pt : l'obligation rend plus
CROISSANCE_MIN = 10.0       # %/an de CA attendu : « en croissance » à partir de là
CROISSANCE_PLAFOND = 15.0   # %/an retenus au plus dans le rendement implicite

FLAGS = ("vert", "orange", "rouge", "na")


def _num(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if v == v and abs(v) != float("inf") else None


def earnings_yield(forward_pe: Any, pe_ttm: Any) -> tuple[Optional[float], Optional[str]]:
    """Inverse du P/E forward s'il est positif, sinon du P/E TTM. En %."""
    fwd, ttm = _num(forward_pe), _num(pe_ttm)
    if fwd is not None and fwd > 0:
        return 100.0 / fwd, "forward"
    if ttm is not None and ttm > 0:
        return 100.0 / ttm, "ttm"
    return None, None


def flag_pour(prime: Optional[float]) -> str:
    if prime is None:
        return "na"
    if prime >= SEUIL_VERT:
        return "vert"
    if prime < SEUIL_ROUGE:
        return "rouge"
    return "orange"


def calculer_prime(
    *,
    taux_10y: Any,
    fcf_yield: Any,
    fcf_ttm: Any,
    forward_pe: Any,
    pe_ttm: Any,
    croissance_ca: Any = None,
    financiere: bool = False,
) -> Dict[str, Any]:
    """Rend le bloc `rendement` de la carte. Toutes les grandeurs sont en %."""
    taux = _num(taux_10y)
    ey, ey_source = earnings_yield(forward_pe, pe_ttm)
    fy, fcf = _num(fcf_yield), _num(fcf_ttm)
    g = _num(croissance_ca)
    en_croissance = g is not None and g >= CROISSANCE_MIN
    g_retenue = min(g, CROISSANCE_PLAFOND) if en_croissance else None

    out: Dict[str, Any] = {
        "version": VERSION,
        "taux_10y": taux,
        "earnings_yield": round(ey, 2) if ey is not None else None,
        "earnings_yield_source": ey_source,
        "prime_ey": round(ey - taux, 2) if ey is not None and taux is not None else None,
        "fcf_yield": round(fy, 2) if fy is not None else None,
        "croissance_ca": round(g, 1) if g is not None else None,
        "croissance_retenue": g_retenue,
        "base": None,            # « fcf », « fcf+croissance », « earnings »
        "rendement": None,       # le rendement comparé au taux
        "prime": None,
        "flag": "na",
        "raison_na": None,
    }
    if taux is None:
        out["raison_na"] = "taux 10 ans indisponible"
        return out

    if financiere:
        # Banque / assurance : pas de FCF qui ait un sens, l'earnings yield le remplace.
        # Sans croissance ajoutée : les bénéfices non distribués financent déjà
        # cette croissance, l'ajouter la compterait deux fois.
        if ey is None:
            out["raison_na"] = "bénéfice négatif ou inconnu"
            return out
        rendement, base = ey, "earnings"
    else:
        if fcf is None or fy is None:
            out["raison_na"] = "FCF inconnu"
            return out
        if fcf <= 0 or fy <= 0:
            out["raison_na"] = "FCF négatif ou nul"
            return out
        rendement, base = fy + (g_retenue or 0.0), "fcf+croissance" if g_retenue else "fcf"

    prime = rendement - taux
    out.update({"base": base, "rendement": round(rendement, 2), "prime": round(prime, 2), "flag": flag_pour(prime)})
    return out
