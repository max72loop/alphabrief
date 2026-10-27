"""Sage — assemblage du contexte du message du matin.

Aucun appel réseau, aucune base : les trois sources (cotations live, libellés,
scores) sont injectées. Ce qui est verrouillé ici, ce sont les règles qui
décident QUOI Sage a le droit de proposer — c'est là que se logent les conseils
absurdes (acheter ce qu'on détient déjà, se fier à une note qui n'en est pas
une, acheter sans savoir avec quel cash).
"""
from __future__ import annotations

import pytest

from core.providers import sage_advisor as S


# Un portefeuille réduit mais représentatif : une ligne à équivalence de
# cotation (GOOGL noté sous GOOG), une ligne notée sous son propre symbole, et
# du cash sans cotation. Montants ronds, vérifiables de tête.
POSITIONS = [
    {"position_id": 1, "actif": "GOOGL", "valeur_live_eur": 6000.0,
     "pnl_pct": 25.0, "change_24h_pct": -0.4},
    {"position_id": 2, "actif": "TSM", "valeur_live_eur": 3000.0,
     "pnl_pct": 16.0, "change_24h_pct": 2.7},
    {"position_id": 3, "actif": "CASH-EUR", "valeur_live_eur": None,
     "derniere_valeur_eur": 1000.0, "pnl_pct": None, "change_24h_pct": None},
]

METAS = {
    1: {"actif": "GOOGL", "libelle": "Alphabet", "classe": "actions"},
    2: {"actif": "TSM", "libelle": "TSMC", "classe": "actions"},
    3: {"actif": "CASH-EUR", "libelle": "Cash disponible", "classe": "cash"},
}

SCORES = {
    "GOOG": {"ticker": "GOOG", "score_total": 64, "score_label": "Exceptionnel"},
    "TSM": {"ticker": "TSM", "score_total": 66, "score_label": "Exceptionnel"},
    "NVDA": {"ticker": "NVDA", "score_total": 60, "score_label": "Exceptionnel"},
    "CS.PA": {"ticker": "CS.PA", "score_total": 70, "score_label": "Données insuffisantes"},
}


@pytest.fixture
def ctx(monkeypatch):
    monkeypatch.setattr(S, "_positions_live", lambda: POSITIONS)
    monkeypatch.setattr(S, "_libelles", lambda: METAS)
    monkeypatch.setattr(S, "_scores", lambda: SCORES)
    return S._contexte({"risk": 4})


def test_total_inclut_le_cash_non_cote(ctx):
    # 6000 + 3000 + 1000 : sans le repli sur la dernière saisie, le cash
    # disparaîtrait du total ET de la contrainte d'achat.
    assert ctx["total_eur"] == pytest.approx(10_000.0)
    assert ctx["cash_eur"] == pytest.approx(1000.0)


def test_le_cash_n_est_pas_une_ligne_a_arbitrer(ctx):
    assert "Cash disponible" not in ctx["lignes"]


def test_ligne_detenue_recoit_la_note_de_son_equivalence(ctx):
    # GOOGL est noté sous GOOG : sans résolution, la ligne serait « pas de note ».
    ligne = [l for l in ctx["lignes"].splitlines() if "GOOGL" in l][0]
    assert "note 64/100 (Exceptionnel)" in ligne
    assert "pas de note" not in ligne


def test_poids_calcule_sur_le_total_live(ctx):
    assert "60% du portefeuille" in ctx["lignes"]  # 6000 / 10000


def test_societe_deja_detenue_absente_des_candidats(ctx):
    # Proposer GOOG à l'achat quand Max détient GOOGL, c'est proposer ce qu'il a.
    assert "GOOG" not in ctx["candidats"]
    assert "TSM" not in ctx["candidats"]


def test_note_sans_verdict_exclue_des_candidats(ctx):
    # CS.PA sort le score le plus haut (70) mais sous la bande « Données
    # insuffisantes » : c'est un aveu d'ignorance, pas une idée d'achat.
    assert "CS.PA" not in ctx["candidats"]
    assert "NVDA" in ctx["candidats"]


def test_pas_de_cotations_pas_de_message(monkeypatch):
    monkeypatch.setattr(S, "_positions_live", lambda: [])
    assert S._contexte({"risk": 4}) is None


def test_portefeuille_a_zero_pas_de_message(monkeypatch):
    monkeypatch.setattr(S, "_positions_live", lambda: [
        {"position_id": 1, "actif": "TSM", "valeur_live_eur": 0.0},
    ])
    monkeypatch.setattr(S, "_libelles", lambda: {1: METAS[2]})
    monkeypatch.setattr(S, "_scores", lambda: SCORES)
    assert S._contexte({"risk": 4}) is None
