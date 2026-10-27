"""Sage × cycle (v2, 2026-09-30) — ce que Sage voit de la phase et de la grille.

Aucun réseau, aucune base : les réponses de l'API Pixel Office sont écrites à
la main. Ce qui est verrouillé : rien d'inventé quand une source manque, la
phase DÉCLARÉE sert de grille, et une seule langue (« Fin de cycle »).
"""
from __future__ import annotations

import pytest

from core.providers import sage_advisor as S

DETECTEUR = {
    "phase": "expansion", "phase_label": "Expansion", "confidence": 62, "stale": False,
    "indicators": [
        {"key": "vix", "name": "VIX", "vote": "expansion", "signal": "15"},
        {"key": "yield_curve", "name": "Courbe des taux", "vote": "expansion", "signal": "+0.6 %"},
        {"key": "small_large", "name": "IWM/SPY", "vote": "expansion", "signal": "+2 %"},
        {"key": "copper_gold", "name": "Cuivre/Or", "vote": "slowdown", "signal": "−4 %"},
    ],
}
LECTURE = {
    "phase": {"key": "slowdown", "label": "Fin de cycle", "faible_discrimination": False,
              "declared_at": "2026-09-30T07:11:36.252Z"},
    "exposition": {"total_positions": 18, "en_tete_pct": 16, "cyclique_pct": 96.7, "defensif_pct": 3.4},
}


def test_secteur_en_tete_dans_la_phase_declaree():
    assert S._secteur_txt("Energy", "slowdown") == " · secteur Énergie · en tête dans cette phase"
    assert S._secteur_txt("Information Technology", "slowdown") == " · secteur Technologie"


def test_secteur_morningstar_normalise():
    assert S._secteur_txt("Healthcare", "slowdown").endswith("en tête dans cette phase")


def test_sans_secteur_ou_inconnu_rien():
    assert S._secteur_txt(None, "slowdown") == ""
    assert S._secteur_txt("Crypto", "slowdown") == ""


def test_sans_phase_declaree_pas_de_en_tete():
    assert S._secteur_txt("Energy", None) == " · secteur Énergie"


def test_bloc_complet_desaccord_et_porteurs():
    bloc = S.bloc_cycle(DETECTEUR, LECTURE)
    assert "phase déclarée par Max : Fin de cycle (depuis le 30/09)" in bloc
    assert "en désaccord avec la phase déclarée" in bloc
    # Les deux plus lourds qui votent Expansion : courbe (3) puis VIX (2), pas IWM (1).
    assert "porté par Courbe des taux +0.6 %, VIX 15" in bloc
    assert "IWM/SPY" not in bloc
    assert "Énergie, Matériaux, Santé, Consommation de base" in bloc
    assert "16 % en tête · 97 % cyclique / 3 % défensif" in bloc


def test_accord():
    lecture = {**LECTURE, "phase": {**LECTURE["phase"], "key": "expansion", "faible_discrimination": True}}
    bloc = S.bloc_cycle(DETECTEUR, lecture)
    assert "en accord avec la phase déclarée" in bloc
    assert "peu informatif en Expansion" in bloc


def test_sans_phase_declaree_dit_absente():
    bloc = S.bloc_cycle(DETECTEUR, {"phase": None, "exposition": LECTURE["exposition"]})
    assert "aucune phase déclarée" in bloc
    assert "accord" not in bloc and "en tête dans cette phase" not in bloc
    assert "en tête ·" not in bloc  # pas de % en tête sans phase


def test_pending_equivaut_a_absente():
    bloc = S.bloc_cycle(DETECTEUR, {"pending": "migration"})
    assert "aucune phase déclarée" in bloc


def test_detecteur_absent():
    bloc = S.bloc_cycle(None, LECTURE)
    assert "détecteur de prix indisponible" in bloc
    assert "Fin de cycle" in bloc


def test_rien_du_tout():
    assert S.bloc_cycle(None, None) is None


def test_libelle_slowdown_unifie():
    bloc = S.bloc_cycle({**DETECTEUR, "phase": "slowdown", "indicators": []}, None)
    assert "Fin de cycle" in bloc and "Ralentissement" not in bloc


def test_contexte_porte_secteurs_lignes_et_candidats(monkeypatch):
    monkeypatch.setattr(S, "_positions_live", lambda: [
        {"position_id": 1, "actif": "XOM", "secteur_gics": "Energy", "valeur_live_eur": 5000.0,
         "pnl_pct": 3.0, "change_24h_pct": 0.1},
        {"position_id": 2, "actif": "BTC", "secteur_gics": None, "valeur_live_eur": 5000.0,
         "pnl_pct": 3.0, "change_24h_pct": 0.1},
    ])
    monkeypatch.setattr(S, "_libelles", lambda: {1: {"classe": "actions"}, 2: {"classe": "crypto"}})
    monkeypatch.setattr(S, "_scores", lambda: {"NVDA": {"ticker": "NVDA", "score_total": 60, "score_label": "Fort"}})
    monkeypatch.setattr(S, "_theses", lambda: {})
    monkeypatch.setattr(S, "_secteurs_notes", lambda: {"NVDA": "Information Technology"})
    ctx = S._contexte({"risk": 3}, phase_key="slowdown")
    xom, btc = ctx["lignes"].split("\n")
    assert "secteur Énergie · en tête dans cette phase" in xom
    assert "secteur" not in btc
    assert ctx["candidats"] == "- NVDA : note 60/100 (Fort) · secteur Technologie"


def test_version_du_prompt():
    assert S.SAGE_PROMPT_VERSION == 2
