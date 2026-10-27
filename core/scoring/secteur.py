"""
Le secteur sous lequel une société est NOTÉE.

Deux défauts corrigés ici le 2026-09-23 :

1. Le moteur lisait le libellé brut de yfinance (taxonomie Morningstar), alors
   que ses tables de seuils (`potential._SECTOR_*_RANGES`) et d'ETF
   (`momentum._SECTOR_ETFS`) sont écrites en GICS. Quatre libellés yfinance n'y
   figuraient pas : « Healthcare », « Consumer Cyclical », « Consumer
   Defensive », « Basic Materials ». Les sociétés de ces secteurs étaient
   notées sur les bornes par défaut et leur momentum comparé au SPY, sans que
   rien ne le dise.

2. Une correction manuelle (`societes.secteur_source = 'manuel'`, posée par Max)
   ne servait qu'à la grille de cycle. Le moteur continuait de noter CHYM
   (néobanque) comme un éditeur de logiciels, parce que yfinance le range en
   « Technology ».

Règle : secteur manuel s'il existe, sinon le libellé yfinance normalisé en GICS
(`core.cycle.mapping.normalize_sector`, déjà la référence de la couche cycle),
puis traduit vers la clef des tables. Libellé inconnu → le brut, inchangé :
jamais de devinette, même contrat que `normalize_sector`.
"""

from __future__ import annotations

import logging
from typing import Optional

from core.cycle.mapping import normalize_sector

logger = logging.getLogger(__name__)

# GICS → clef des tables du moteur, là où elles diffèrent.
#  - Les tables disent « Technology » (le libellé historique de yfinance) et
#    pas « Information Technology ».
#  - « Financials » et « Financial Services » sont DEUX barèmes dans les
#    tables : bancaire (P/E 7-18, CAGR 2-12) contre fintech (P/E 12-45, CAGR
#    5-25). Toutes les financières de yfinance arrivent en « Financial
#    Services » et ont toujours été notées sur le second ; le GICS les
#    confondant, on les y renvoie. Traduire en « Financials » basculait V, NU,
#    SOFI, COIN… sur le barème bancaire (mesuré le 2026-09-23, 4 bandes bougées).
_GICS_VERS_MOTEUR = {
    "Information Technology": "Technology",
    "Financials": "Financial Services",
}


def secteur_moteur(brut: Optional[str], manuel: Optional[str] = None) -> str:
    """Le libellé à passer aux tables du moteur."""
    gics = normalize_sector(manuel) if manuel else None
    if gics is None:
        gics = normalize_sector(brut)
    if gics is None:
        return brut or ""
    return _GICS_VERS_MOTEUR.get(gics, gics)


def secteur_manuel(ticker: str) -> Optional[str]:
    """Le secteur GICS corrigé à la main pour `ticker`, ou None.

    Lu sous le ticker NOTÉ (GOOGL → GOOG), comme `these`. Une base injoignable
    ne doit pas empêcher de noter : on loggue et on retombe sur yfinance.
    """
    try:
        from core.scoring import listings
        from core.storage import db

        scored = (listings.resolve(ticker) or ticker).upper()
        rows = db.query(
            "SELECT secteur_gics FROM societes "
            "WHERE ticker = %s AND secteur_source = 'manuel' AND secteur_gics IS NOT NULL",
            [scored],
        )
        return rows[0]["secteur_gics"] if rows else None
    except Exception as e:  # noqa: BLE001 — le score passe avant la correction
        logger.warning(f"secteur manuel illisible pour {ticker} : {e}")
        return None
