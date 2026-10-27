"""Secteur de notation et bénéfice exceptionnel (2026-09-23).

Cas réels : CHYM (néobanque que yfinance range en « Technology », P/E 5,6x
avec ROE négatif et forward P/E 17,8x), et les quatre libellés yfinance
qu'aucune table du moteur ne connaissait.
"""

from core.features.momentum import _SECTOR_ETFS
from core.scoring import potential
from core.scoring.importance import build_importance_items
from core.scoring.potential import benefice_exceptionnel, compute_potential_score
from core.scoring.secteur import secteur_moteur


# --- Secteur de notation ---------------------------------------------------

def test_libelles_yfinance_traduits_vers_les_tables():
    assert secteur_moteur("Healthcare") == "Health Care"
    assert secteur_moteur("Consumer Cyclical") == "Consumer Discretionary"
    assert secteur_moteur("Consumer Defensive") == "Consumer Staples"
    assert secteur_moteur("Basic Materials") == "Materials"
    assert secteur_moteur("Technology") == "Technology"


def test_les_financieres_gardent_leur_bareme_fintech():
    """Les tables distinguent « Financials » (bancaire) de « Financial Services »
    (fintech) ; toutes les financières yfinance ont toujours été notées sur le
    second. La traduction ne doit pas les faire changer de barème."""
    assert secteur_moteur("Financial Services") == "Financial Services"
    assert secteur_moteur("Technology", manuel="Financials") == "Financial Services"


def test_tout_libelle_yfinance_trouve_son_etf_et_ses_bornes():
    """Le défaut d'origine : ces secteurs retombaient sur SPY et les bornes par défaut."""
    for brut in ["Technology", "Financial Services", "Healthcare", "Consumer Cyclical",
                 "Consumer Defensive", "Communication Services", "Industrials", "Energy",
                 "Basic Materials", "Utilities", "Real Estate"]:
        cle = secteur_moteur(brut)
        assert cle in _SECTOR_ETFS, (brut, cle)
        assert cle in potential._SECTOR_PE_RANGES, (brut, cle)


def test_le_secteur_manuel_gagne():
    assert secteur_moteur("Healthcare", manuel="Information Technology") == "Technology"


def test_libelle_inconnu_rendu_tel_quel():
    assert secteur_moteur("Conglomerates") == "Conglomerates"
    assert secteur_moteur(None) == ""
    assert secteur_moteur("Technology", manuel="n'importe quoi") == "Technology"


# --- Bénéfice exceptionnel -------------------------------------------------

def test_signatures_du_benefice_exceptionnel():
    assert benefice_exceptionnel(5.6, 17.8, -1.3)       # CHYM : les deux signatures
    assert benefice_exceptionnel(8.0, 20.0, 15.0)       # forward > 2 × TTM
    assert benefice_exceptionnel(8.0, None, -2.0)       # ROE négatif seul
    assert not benefice_exceptionnel(15.0, 25.0, 12.0)  # forward 1,67 × TTM : baisse, pas exception
    assert not benefice_exceptionnel(-4.0, 20.0, -8.0)  # déficitaire : déjà traité comme perte
    assert not benefice_exceptionnel(None, 17.8, -1.3)


def _carte(pe, forward_pe, roe, peg=None):
    return {
        "identity": {"sector": "Technology", "industry": "Software - Application"},
        "financials": {"roe": roe, "revenue_cagr_3y": 29.4},
        "valuation": {"pe_ttm": pe, "forward_pe": forward_pe, "peg_ratio": peg},
        "market": {}, "technicals": {},
    }


def test_le_pilier_valeur_ignore_le_pe_exceptionnel():
    """Avec le garde-fou, un P/E de 5,6 ne doit pas noter mieux qu'un P/E absent."""
    avec = compute_potential_score(_carte(5.6, 17.8, -1.3, peg=0.19))["pillars"]["value"]
    sans = compute_potential_score(_carte(None, 17.8, -1.3))["pillars"]["value"]
    assert avec == sans


def test_un_pe_sain_compte_toujours():
    bas = compute_potential_score(_carte(8.0, 7.0, 20.0))["pillars"]["value"]
    haut = compute_potential_score(_carte(40.0, 35.0, 20.0))["pillars"]["value"]
    assert bas > haut


def test_la_fiche_ne_vante_plus_le_pe_ecarte():
    card = _carte(5.6, 17.8, -1.3, peg=0.19)
    labels = {i["label"] for i in build_importance_items(card, limit=50)}
    assert "Bénéfice exceptionnel probable" in labels
    assert "P/E attractif (value)" not in labels
    assert "PEG attractif" not in labels
    assert "Baisse bénéfices attendue" not in labels
