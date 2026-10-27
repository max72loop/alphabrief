"""Prime de rendement contre le 10 ans et dilution par an (2026-10-27).

Chaque attendu est calculé à la main dans le commentaire du cas.
"""
from datetime import date

import pytest

from core.providers.rendement import croissance_depuis_estimations
from core.scoring.dilution import annualiser, calculer_dilution
from core.scoring.potential import compute_share_dilution_score, est_banque_ou_assurance
from core.scoring.prime import calculer_prime, earnings_yield, flag_pour


def _prime(**kw):
    base = dict(taux_10y=5.0, fcf_yield=7.2, fcf_ttm=1e9, forward_pe=15.0, pe_ttm=14.0, croissance_ca=None)
    base.update(kw)
    return calculer_prime(**base)


# ── Prime ───────────────────────────────────────────────────────────────────
def test_cas_general_fcf_yield_moins_taux():
    r = _prime()                                   # 7,2 − 5,0 = +2,2 ≥ +2 → vert
    assert r["base"] == "fcf" and r["prime"] == pytest.approx(2.2) and r["flag"] == "vert"
    assert r["earnings_yield"] == pytest.approx(6.67, abs=0.01)   # 100 / 15
    assert r["earnings_yield_source"] == "forward"
    assert r["prime_ey"] == pytest.approx(1.67, abs=0.01)


def test_croissance_plafonnee_a_15():
    r = _prime(fcf_yield=2.0, croissance_ca=30.0)  # 2 + min(30, 15) − 5 = +12
    assert r["base"] == "fcf+croissance" and r["croissance_retenue"] == 15.0
    assert r["rendement"] == pytest.approx(17.0) and r["prime"] == pytest.approx(12.0)


def test_croissance_sous_10_n_est_pas_ajoutee():
    r = _prime(fcf_yield=4.0, croissance_ca=8.0)   # 4 − 5 = −1 : pile la borne → orange
    assert r["base"] == "fcf" and r["croissance_retenue"] is None
    assert r["prime"] == pytest.approx(-1.0) and r["flag"] == "orange"


def test_seuils():
    assert flag_pour(2.0) == "vert"      # ≥ +2
    assert flag_pour(1.99) == "orange"
    assert flag_pour(-1.0) == "orange"   # rouge strictement sous −1
    assert flag_pour(-1.01) == "rouge"
    assert flag_pour(None) == "na"


def test_fcf_negatif_donne_na_et_garde_l_earnings_yield():
    # Néocloud : FCF négatif → jamais de rouge automatique, l'EY forward reste lu.
    r = _prime(fcf_yield=-12.0, fcf_ttm=-3e9, forward_pe=50.0)
    assert r["flag"] == "na" and r["prime"] is None and r["raison_na"] == "FCF négatif ou nul"
    assert r["earnings_yield"] == pytest.approx(2.0)                # 100 / 50
    assert r["prime_ey"] == pytest.approx(-3.0)                     # 2 − 5


def test_fcf_nul_ou_inconnu_donne_na():
    assert _prime(fcf_yield=0.0, fcf_ttm=0.0)["flag"] == "na"
    assert _prime(fcf_yield=None, fcf_ttm=None)["raison_na"] == "FCF inconnu"


def test_banque_passe_a_l_earnings_yield_sans_croissance():
    # NU : forward P/E 11,16 → EY 8,96 ; 8,96 − 5 = +3,96. Croissance 30 % ignorée.
    r = _prime(financiere=True, forward_pe=11.16, fcf_yield=5.2, croissance_ca=30.0)
    assert r["base"] == "earnings" and r["prime"] == pytest.approx(3.96, abs=0.01) and r["flag"] == "vert"


def test_sans_taux_pas_de_flag():
    assert _prime(taux_10y=None)["flag"] == "na"


def test_earnings_yield_repli_ttm_et_perte():
    assert earnings_yield(None, 20.0) == (5.0, "ttm")
    assert earnings_yield(-30.0, 25.0) == (4.0, "ttm")     # forward négatif ignoré
    assert earnings_yield(-30.0, -40.0) == (None, None)


def test_banque_detectee_comme_le_moteur():
    assert est_banque_ou_assurance("Financial Services", "Banks - Regional") is True
    assert est_banque_ou_assurance("Financial Services", "Financial Data & Stock Exchanges") is False  # COIN


# ── Dilution ────────────────────────────────────────────────────────────────
def test_annualiser():
    assert annualiser(33.1, 3) == pytest.approx(10.0, abs=1e-9)   # 1,331^(1/3) = 1,1
    assert annualiser(-100, 3) is None


def test_fenetres_1_et_3_ans():
    # T0 = 133,1 ; T−4 = 121 (→ +10 %/an) ; T−12 = 100 (→ 1,331 sur 3 ans = +10 %/an).
    serie = [133.1, 130, 127, 124, 121, 118, 115, 112, 110, 107, 105, 102, 100]
    d = calculer_dilution(serie)
    assert d["dilution_1y"] == pytest.approx(10.0, abs=0.01)
    assert d["dilution_3y"] == pytest.approx(10.0, abs=0.01)
    assert d["retenue"] == pytest.approx(10.0, abs=0.01)
    assert not d["evenement_1y"] and not d["evenement_3y"]


def test_on_retient_la_pire_fenetre():
    # 1 an : 105/100 = +5 % ; 3 ans : 105/120 → −4,35 %/an. Retenue = +5.
    serie = [105, 104, 103, 101, 100, 104, 108, 110, 112, 115, 117, 119, 120]
    d = calculer_dilution(serie)
    assert d["dilution_1y"] == pytest.approx(5.0, abs=0.01)
    assert d["dilution_3y"] < 0
    assert d["retenue"] == pytest.approx(5.0, abs=0.01)


def test_evenement_sur_le_capital_n_entre_pas_dans_la_note():
    # NBIS 2024 : 372 M → 240 M d'un trimestre à l'autre (−35 %), sortie de Yandex.
    serie = [280, 270, 260, 250, 240, 240, 240, 240, 372, 372, 372, 372, 372]
    d = calculer_dilution(serie)
    assert d["evenement_3y"] is True and d["evenement_1y"] is False
    assert d["dilution_1y"] == pytest.approx(16.67, abs=0.01)     # 280 / 240
    assert d["retenue"] == pytest.approx(16.67, abs=0.01)         # seule la fenêtre propre compte


def test_une_hausse_brutale_reste_une_dilution():
    # IREN : augmentations de capital, +40 % d'un trimestre à l'autre. Ce n'est pas un
    # « événement » à écarter, c'est la dilution elle-même : 196 / 100 → +96 %/an.
    serie = [196, 140, 130, 110, 100]
    d = calculer_dilution(serie)
    assert d["evenement_1y"] is False
    assert d["retenue"] == pytest.approx(96.0)


def test_fenetre_avant_ipo_ecartee():
    # CRCL, IPO le 2025-06-04 : T−4 clôt le 2025-06-30, avant IPO + 90 j (2025-09-02).
    serie = [268.6, 242.3, 242.3, 234.2, 107.5]
    dates = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30"]
    d = calculer_dilution(serie, dates=dates, ipo_date="2025-06-04")
    assert d["avant_ipo_1y"] is True and d["dilution_1y"] is None and d["retenue"] is None
    # Même série, IPO ancienne : la fenêtre est calculée (268,6 / 107,5 → +149,9 %/an).
    d = calculer_dilution(serie, dates=dates, ipo_date="1997-10-09")
    assert d["avant_ipo_1y"] is False and d["dilution_1y"] == pytest.approx(149.86, abs=0.01)


def test_avant_ipo_bloque_aussi_le_repli_annuel():
    # CRWV, IPO le 2025-03-28 : T−12 (2023-06-30) est avant la cotation. Le repli sur
    # les comptes annuels ne doit pas réintroduire une dilution d'avant l'IPO.
    serie = [100] * 13
    dates = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30", "2025-03-31",
             "2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31", "2023-12-31", "2023-09-30", "2023-06-30"]
    d = calculer_dilution(serie, dilution_3y_annuelle_total=50.0, dates=dates, ipo_date="2025-03-28")
    assert d["avant_ipo_1y"] is False and d["dilution_1y"] == pytest.approx(0.0)
    assert d["avant_ipo_3y"] is True and d["dilution_3y"] is None


def test_serie_trop_courte_ne_laisse_pas_le_repli_annuel_passer_l_ipo():
    # CRWV réel (27/10) : 11 trimestres seulement chez FMP, IPO le 2025-03-28. Sans
    # T−12, le repli annuel donnait +33,8 %/an sur une période d'avant la cotation.
    serie = [100] * 11
    dates = ["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30", "2025-06-30", "2025-03-31",
             "2024-12-31", "2024-09-30", "2024-06-30", "2024-03-31", "2023-12-31"]
    d = calculer_dilution(serie, dilution_3y_annuelle_total=139.0, dates=dates, ipo_date="2025-03-28")
    assert d["avant_ipo_3y"] is True and d["dilution_3y"] is None
    assert d["retenue"] == pytest.approx(0.0)                      # seul le 1 an, propre, compte


def test_historique_court_et_repli_annuel():
    d = calculer_dilution([110, 108, 106, 104, 100])               # 5 trimestres : 1 an seulement
    assert d["dilution_1y"] == pytest.approx(10.0) and d["dilution_3y"] is None
    d = calculer_dilution([], dilution_3y_annuelle_total=33.1)     # comptes annuels seuls
    assert d["dilution_3y"] == pytest.approx(10.0, abs=0.01) and d["source"] == "annuel"


def test_bareme_par_an():
    assert compute_share_dilution_score(None) == 50.0
    assert compute_share_dilution_score(-2.0) == 60.0   # rachats nets : bonus léger
    assert compute_share_dilution_score(2.5) == 50.0
    assert compute_share_dilution_score(4.0) == 35.0    # > 3 %/an : pénalité
    assert compute_share_dilution_score(8.0) == 20.0
    assert compute_share_dilution_score(12.0) == 10.0


# ── Consensus ───────────────────────────────────────────────────────────────
def test_croissance_consensus_exercice_passe_vers_suivant():
    rows = [
        {"date": "2027-12-31", "revenueAvg": 121},
        {"date": "2025-12-31", "revenueAvg": 100},
        {"date": "2026-12-31", "revenueAvg": 110},
    ]
    # Exercice en cours = 2026 ; 2025 → 2027 : (121 / 100)^(1/2) − 1 = +10 %/an.
    assert croissance_depuis_estimations(rows, date(2026, 10, 27)) == pytest.approx(10.0)


def test_croissance_consensus_sans_exercice_passe():
    rows = [{"date": "2026-12-31", "revenueAvg": 100}, {"date": "2027-12-31", "revenueAvg": 130},
            {"date": "2028-12-31", "revenueAvg": 144}]
    assert croissance_depuis_estimations(rows, date(2026, 10, 27)) == pytest.approx(20.0)  # (1,44)^½ − 1
    assert croissance_depuis_estimations(rows[:2], date(2026, 10, 27)) is None
