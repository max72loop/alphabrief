"""Résultats trimestriels — calculs purs, cas connus vérifiés à la main.

Chiffres GOOG (yfinance, 28/09/2026) : publication du 22/07/2026, BPA attendu
2,91, publié 2,85 → (2,85 − 2,91) / 2,91 = −2,06 % → « raté ».
Publication du 29/04/2026 : 2,63 attendu, 2,76 publié → +4,94 % → « battu ».
"""
from datetime import date

from core.providers import trimestres_yf as tq


def test_surprise_cas_connus():
    assert tq.surprise_pct(2.91, 2.85) == -2.06
    assert tq.surprise_pct(2.63, 2.76) == 4.94
    # attendu négatif : une perte moins forte que prévu est une bonne surprise
    assert tq.surprise_pct(-0.50, -0.40) == 20.0


def test_surprise_manquante():
    assert tq.surprise_pct(None, 2.85) is None
    assert tq.surprise_pct(2.91, float("nan")) is None
    assert tq.surprise_pct(0, 0.1) is None


def test_verdict_seuils():
    assert tq.verdict(-2.06) == "rate"
    assert tq.verdict(4.94) == "battu"
    assert tq.verdict(1.99) == "conforme"
    assert tq.verdict(-1.99) == "conforme"
    assert tq.verdict(2.0) == "battu"
    assert tq.verdict(-2.0) == "rate"
    assert tq.verdict(None) is None


def test_rattacher_trimestre_publie():
    fins = [date(2026, 6, 30), date(2026, 3, 31), date(2025, 12, 31)]
    assert tq.rattacher(date(2026, 7, 22), fins) == date(2026, 6, 30)
    assert tq.rattacher(date(2026, 4, 29), fins) == date(2026, 3, 31)
    # clôture le jour même : pas encore publiée ce jour-là
    assert tq.rattacher(date(2026, 6, 30), fins) == date(2026, 3, 31)
    # plus de 120 jours après toute clôture connue : pas de devinette
    assert tq.rattacher(date(2027, 2, 1), fins) is None


def test_un_an_avant_exercice_decale():
    fins = [date(2026, 6, 28), date(2025, 6, 29), date(2025, 3, 30)]
    assert tq.un_an_avant(date(2026, 6, 28), fins) == date(2025, 6, 29)
    assert tq.un_an_avant(date(2025, 3, 30), fins) is None


def test_construire_lignes():
    pubs = [
        {"date": date(2026, 10, 28), "bpa_attendu": 3.03, "bpa_publie": float("nan")},
        {"date": date(2026, 7, 22), "bpa_attendu": 2.91, "bpa_publie": 2.85},
    ]
    trims = {
        date(2026, 6, 30): {"ca": 110e9, "resultat_net": 30e9},
        date(2025, 6, 30): {"ca": 96e9, "resultat_net": 28e9},
    }
    lignes = tq.construire_lignes("GOOG", pubs, trims, {"avg": 127.3e9, "year_ago": 102.3e9}, "USD", date(2026, 9, 29))
    a_venir, passe = lignes
    assert a_venir["bpa_publie"] is None and a_venir["verdict"] is None
    assert a_venir["ca_attendu"] == 127.3e9 and a_venir["ca_un_an_avant"] == 102.3e9
    assert passe["verdict"] == "rate" and passe["surprise_pct"] == -2.06
    assert passe["fin_trimestre"] == date(2026, 6, 30)
    assert passe["ca"] == 110e9 and passe["ca_un_an_avant"] == 96e9
    assert passe["ca_attendu"] is None


def test_prompt_lecture_contient_these_et_croissance():
    l = {"date_publication": date(2026, 7, 22), "bpa_publie": 2.85, "bpa_attendu": 2.91,
         "surprise_pct": -2.06, "ca": 110e9, "ca_un_an_avant": 100e9, "devise": "USD"}
    p = tq.prompt_lecture("Alphabet", [l], "Le cloud porte la croissance")
    assert "+10.0 % sur un an" in p and "Le cloud porte la croissance" in p and "110.00 Md USD" in p


def test_consensus_ca_nul_est_inconnu():
    # RIO.AX (semestriel) : yfinance rend 0 comme consensus de CA
    pubs = [{"date": date(2027, 2, 18), "bpa_attendu": None, "bpa_publie": None}]
    (l,) = tq.construire_lignes("RIO.AX", pubs, {}, {"avg": 0, "year_ago": 0}, "USD", date(2026, 9, 29))
    assert l["ca_attendu"] is None and l["ca_un_an_avant"] is None


def test_ecriture_garde_le_ca_et_complete_un_an_avant():
    """Sur la MIROIR uniquement : jamais d'écriture de test sur la vraie base."""
    import os
    import pytest
    if "alphabrief_mirror" not in os.environ.get("ALPHABRIEF_DSN", ""):
        pytest.skip("écrit en base : ALPHABRIEF_DSN doit viser alphabrief_mirror")
    from core.storage import db

    t = "__TEST_TQ__"
    j = date(2026, 9, 29)
    base = {"ticker": t, "bpa_attendu": 1.0, "surprise_pct": 0.0, "verdict": "conforme",
            "ca_attendu": None, "resultat_net": None, "devise": "USD", "bpa_publie": 1.0}
    try:
        tq._ecrire(t, [
            {**base, "date_publication": date(2025, 7, 20), "fin_trimestre": date(2025, 6, 30), "ca": 90e9, "ca_un_an_avant": None},
            {**base, "date_publication": date(2026, 7, 20), "fin_trimestre": date(2026, 6, 30), "ca": 100e9, "ca_un_an_avant": None},
        ], j)
        # synchro suivante : yfinance n'a plus le CA de 2025
        tq._ecrire(t, [
            {**base, "date_publication": date(2025, 7, 20), "fin_trimestre": None, "ca": None, "ca_un_an_avant": None},
        ], j)
        rows = {r["date_publication"]: r for r in db.query(
            "SELECT date_publication, ca, ca_un_an_avant, fin_trimestre FROM resultats_trimestriels WHERE ticker = %s", (t,))}
        assert float(rows[date(2025, 7, 20)]["ca"]) == 90e9
        assert rows[date(2025, 7, 20)]["fin_trimestre"] == date(2025, 6, 30)
        assert float(rows[date(2026, 7, 20)]["ca_un_an_avant"]) == 90e9
    finally:
        with db.connection() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM resultats_trimestriels WHERE ticker = %s", (t,))
