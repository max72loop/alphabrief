"""Règles des catégories de Peter Lynch — cas réels figés (ticker_scores du 2026-10-04)."""
import json
import re
from pathlib import Path

import pytest

from core.lynch import categories as C

_MIGRATION = Path(__file__).resolve().parents[3] / "migrations" / "2026_10_04_lynch.sql"


@pytest.mark.parametrize("fin, secteur, attendu", [
    ({"revenue_cagr_3y": 100.045, "net_income": 1.9e11}, "Information Technology", "fast"),   # NVDA
    ({"revenue_cagr_3y": 16.124, "net_income": 1.3e11}, "Information Technology", "stalwart"),  # MSFT
    ({"revenue_cagr_3y": 6.64, "net_income": 9.2e9}, "Consumer Staples", "stalwart"),          # COST
    ({"revenue_cagr_3y": 3.689, "net_income": 1.4e10}, "Consumer Staples", "slow"),            # KO
    ({"revenue_cagr_3y": -4.501, "net_income": 4.9e9}, "Industrials", "cyclical"),             # DE
    ({"revenue_cagr_3y": -5.713, "net_income": -1.1e10}, "Information Technology", "turnaround"),  # INTC
    ({"revenue_cagr_3y": 31.0, "net_income": -9.9e8}, "Financials", "fast"),                   # COIN
])
def test_cas_reels(fin, secteur, attendu):
    assert C.classer(fin, secteur)[0] == attendu


def test_redressement_passe_avant_cyclique():
    assert C.classer({"revenue_cagr_3y": -3, "net_income": -1}, "Energy")[0] == "turnaround"


def test_croissance_rapide_en_perte_le_dit():
    cle, regle = C.classer({"revenue_cagr_3y": 44.6, "net_income": -1.5e9}, "Information Technology")
    assert cle == "fast" and "perte" in regle


def test_regle_lisible():
    assert C.classer({"revenue_cagr_3y": 18.938, "net_income": 1}, None)[1] == "CA +18,9 %/an sur 3 ans"


@pytest.mark.parametrize("fin", [None, {}, {"revenue_cagr_3y": None}, {"revenue_cagr_3y": "n/a"},
                                 {"revenue_cagr_3y": float("nan")}])
def test_ne_devine_jamais_sans_croissance(fin):
    assert C.classer(fin, "Information Technology")[0] is None


def test_cyclique_sans_croissance_connue():
    assert C.classer({}, "Materials")[0] == "cyclical"


def test_valeur_actifs_jamais_proposee():
    vus = {C.classer({"revenue_cagr_3y": g, "net_income": n}, s)[0]
           for g in (-50, 0, 4.9, 5, 19.9, 20, 300) for n in (-1, 0, 1, None)
           for s in (None, "Energy", "Financials", "Real Estate")}
    assert not (vus & C.MANUAL_ONLY)


def test_la_contrainte_check_sql_liste_les_six_cles():
    sql = _MIGRATION.read_text(encoding="utf-8")
    bloc = re.search(r"lynch_categorie IN \((.*?)\)\s*\);", sql, re.S)
    assert bloc
    assert set(re.findall(r"'([^']+)'", bloc.group(1))) == set(C.KEYS)


def test_chaque_categorie_est_complete():
    for k, v in C.CATEGORIES.items():
        assert v["label"] and v["emoji"] and v["definition"], k
        assert 2 <= len(v["surveiller"]) <= 3, k


def test_export_json_est_le_describe(tmp_path):
    p = C.export(tmp_path / "l.json")
    data = json.loads(p.read_text(encoding="utf-8"))
    data.pop("_generated_by")
    assert data == json.loads(json.dumps(C.describe(), ensure_ascii=False))
