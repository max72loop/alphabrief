"""Score en ombre — cas connus vérifiés à la main."""

import pytest

from core.scoring import ombre

REF = {
    "Technology": {
        "rentabilite": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
        "valorisation": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08],
        "croissance": [0, 5, 10, 15, 20, 25, 30, 35],
        "solidite": [-1, 0, 0.5, 1, 1.5, 2, 3, 4],
    },
    "Energy": {"rentabilite": [1, 2, 3]},  # trop peu de sociétés : repli sur _tous
    "_tous": {"rentabilite": [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]},
}


def test_percentile_au_milieu_et_aux_bords():
    d = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert ombre.percentile(5.5, d, +1) == 50.0      # 5 valeurs dessous sur 10
    assert ombre.percentile(0, d, +1) == 0.0
    assert ombre.percentile(11, d, +1) == 100.0
    assert ombre.percentile(5, d, +1) == 45.0        # ex æquo : rang moyen (4+5)/2/10
    assert ombre.percentile(5, d, -1) == 55.0        # plus bas = mieux


def test_momentum_12_1_relatif_a_la_main():
    # Titre +32 % sur 12 mois dont +10 % le dernier mois → 1,32/1,10 − 1 = +20 %
    # ETF : 32 − 12 = +20 % sur 12 mois, 10 − 5 = +5 % sur 1 mois → 1,20/1,05 − 1 = +14,2857 %
    m = {"momentum_12m": 32, "momentum_1m": 10, "relative_momentum_12m": 12, "relative_momentum_1m": 5}
    assert ombre.momentum_12_1_relatif(m) == pytest.approx(5.71, abs=0.01)
    assert ombre.momentum_12_1_relatif({"momentum_12m": 32}) is None


def test_score_moyenne_des_percentiles_du_secteur():
    card = {
        "identity": {"sector_note": "Technology"},
        "financials": {"roa": 5.5, "revenue_cagr_3y": 17.5, "net_debt_to_ebitda": 1.25},
        "valuation": {"forward_pe": 20},  # rendement 0,05 → 4 dessous sur 8, ex æquo → 56,25
    }
    s = ombre.score_ombre(card, REF)
    assert s["detail"] == {"rentabilite": 50.0, "valorisation": 56.2, "croissance": 50.0, "solidite": 50.0}
    # (50 + 56,2 + 50 + 50) / 4 = 51,55, sur les percentiles déjà arrondis
    assert s["fondamentaux"] == pytest.approx(51.55, abs=0.06)
    assert s["version"] == ombre.VERSION


def test_perte_classee_en_bas_et_forward_prioritaire():
    card = {"identity": {"sector_note": "Technology"},
            "financials": {"roa": 5.5}, "valuation": {"forward_pe": -10, "pe_ttm": 15}}
    assert ombre.score_ombre(card, REF)["detail"]["valorisation"] == 0.0


def test_secteur_trop_petit_retombe_sur_l_echantillon_entier():
    card = {"identity": {"sector_note": "Energy"}, "financials": {"roa": 45}, "valuation": {}}
    assert ombre.score_ombre(card, REF)["detail"]["rentabilite"] == 50.0


def test_moins_de_deux_metriques_pas_de_verdict():
    card = {"identity": {"sector_note": "Technology"}, "financials": {"roa": 5.5}, "valuation": {}}
    s = ombre.score_ombre(card, REF)
    assert s["fondamentaux"] is None
    assert s["detail"]["rentabilite"] == 50.0
