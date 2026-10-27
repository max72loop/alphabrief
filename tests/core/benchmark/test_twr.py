"""TWR de la poche actions et écarts aux benchmarks — cas calculés à la main."""
from datetime import date

import pytest

from core.benchmark.twr import benchmark, bilan, dernier_cours, twr_indice, twr_lignes

J = [date(2026, 8, 24), date(2026, 8, 25), date(2026, 8, 26)]


def test_dernier_cours_week_end():
    s = {date(2026, 8, 21): 10.0}
    assert dernier_cours(s, date(2026, 8, 23)) == 10.0      # dimanche → clôture du vendredi
    assert dernier_cours(s, date(2026, 8, 20)) is None


def test_twr_deux_lignes():
    # Veille : A = 10 × 10 = 100, B = 1 × 100 = 100 → 200. Jour 2 : 10 × 11 + 1 × 90 = 200 → +0 %.
    # Jour 3 : 10 × 12 + 1 × 99 = 219 contre 200 → ×1,095.
    q = {"A": {d: 10 for d in J}, "B": {d: 1 for d in J}}
    c = {"A": dict(zip(J, [10, 11, 12])), "B": dict(zip(J, [100, 90, 99]))}
    idx = twr_lignes(J, q, c)
    assert [round(v, 4) for _, v in idx] == [1.0, 1.0, 1.095]


def test_une_ligne_achetee_n_entre_que_le_lendemain():
    # B est achetée le 25 (quantité 0 la veille) : le 25 ne mesure que A (+10 %),
    # le 26 mesure A et B : (10 × 12 + 1 × 120) / (10 × 11 + 1 × 100) = 240 / 210.
    q = {"A": {d: 10 for d in J}, "B": {J[1]: 1, J[2]: 1}}
    c = {"A": dict(zip(J, [10, 11, 12])), "B": dict(zip(J, [100, 100, 120]))}
    idx = twr_lignes(J, q, c)
    assert idx[1][1] == pytest.approx(1.1)
    assert idx[2][1] == pytest.approx(1.1 * 240 / 210)


def test_un_apport_ne_cree_pas_de_performance():
    # Doubler la quantité de A le 25 à cours inchangé : TWR nul, alors que la valeur double.
    q = {"A": {J[0]: 10, J[1]: 20, J[2]: 20}}
    c = {"A": dict(zip(J, [10, 10, 10]))}
    assert [v for _, v in twr_lignes(J, q, c)] == [1.0, 1.0, 1.0]


def test_twr_indice_base_1():
    assert [v for _, v in twr_indice(J, dict(zip(J, [80.0, 84.0, 88.0])))] == [1.0, 1.05, 1.1]


def test_bilan_ecarts_et_objectif_au_prorata():
    # 73 jours : objectif = 3,5 × 73 / 365 = 0,70 pt. Poche +6 %, monde +4 % → +2 pts bruts, +1,30 vs objectif.
    b = bilan(date(2026, 8, 23), date(2026, 11, 4), 1.06, 1.04, 1.08)
    assert b["jours"] == 73 and b["objectif_pts"] == 0.7
    assert b["ecart_brut_pts"] == 2.0 and b["ecart_objectif_pts"] == 1.3
    assert b["ecart_nasdaq_pts"] == -2.0


def test_benchmark_suivi_court():
    jours = [date(2026, 8, 24), date(2026, 10, 27)]
    poche = [(jours[0], 1.0), (jours[1], 1.10)]
    monde = [(jours[0], 1.0), (jours[1], 1.05)]
    nasdaq = [(jours[0], 1.0), (jours[1], 1.12)]
    out = benchmark(jours, poche, monde, nasdaq, date(2026, 10, 27))
    a = out["annee"]
    assert a["annee"] == 2026 and a["annee_complete"] is False         # suivi ouvert le 24/08
    assert a["poche_pct"] == 10.0 and a["monde_pct"] == 5.0 and a["ecart_brut_pts"] == 5.0
    g = out["glissant"]
    assert g["complet"] is False and g["complet_le"] == "2029-08-24"
    assert "poche_pct_an" not in g                                       # pas d'annualisation d'une période courte


def test_benchmark_glissant_complet_annualise():
    jours = [date(2023, 10, 27), date(2025, 12, 31), date(2026, 10, 27)]
    poche = [(jours[0], 1.0), (jours[1], 1.2), (jours[2], 1.331)]
    monde = [(jours[0], 1.0), (jours[1], 1.1), (jours[2], 1.157625)]
    out = benchmark(jours, poche, monde, monde, date(2026, 10, 27))
    g = out["glissant"]
    assert g["complet"] is True
    # 1,331 sur 1096 jours (2024 bissextile) ≈ 10 %/an ; 1,157625 ≈ 5 %/an.
    assert g["poche_pct_an"] == pytest.approx(9.99, abs=0.02)
    assert g["monde_pct_an"] == pytest.approx(5.0, abs=0.02)
    a = out["annee"]
    assert a["debut"] == "2025-12-31" and a["annee_complete"] is True
    assert a["poche_pct"] == pytest.approx(10.92, abs=0.01)             # 1,331 / 1,2
