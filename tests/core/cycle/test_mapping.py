"""Le mapping secteur → phase est une constante versionnée : ces tests
verrouillent sa forme, sa cohérence avec le schéma SQL et la fidélité au
modèle de référence (Stovall / Fidelity) tel que Max l'a spécifié.
"""

import re
from pathlib import Path

from core.cycle import mapping

_ROOT = Path(__file__).resolve().parents[3]
_MIGRATION = _ROOT / "migrations" / "2026_09_19_cycle.sql"


def test_onze_secteurs_gics_et_partage_cyclique_defensif():
    assert len(mapping.SECTORS) == 11
    assert mapping.DEFENSIVE == {"Consumer Staples", "Health Care", "Utilities"}
    assert mapping.CYCLICAL | mapping.DEFENSIVE == set(mapping.SECTORS)
    assert not (mapping.CYCLICAL & mapping.DEFENSIVE)


def test_quatre_phases_dans_l_ordre_du_cycle_memes_cles_que_le_detecteur():
    from core.bitcoin.cycle_detector import PHASE_LABELS

    assert mapping.PHASE_KEYS == ("recovery", "expansion", "slowdown", "recession")
    assert set(mapping.PHASE_KEYS) == set(PHASE_LABELS)


def test_la_table_est_celle_du_modele_de_reference():
    """Mot pour mot la table de la spécification (secteurs GICS)."""
    assert mapping.LEADERS == {
        "recovery": ("Consumer Discretionary", "Financials", "Real Estate", "Industrials"),
        "expansion": ("Information Technology", "Communication Services", "Industrials", "Consumer Discretionary"),
        "slowdown": ("Energy", "Materials", "Health Care", "Consumer Staples"),
        "recession": ("Consumer Staples", "Health Care", "Utilities", "Communication Services"),
    }
    for leaders in mapping.LEADERS.values():
        assert set(leaders) <= set(mapping.SECTORS)


def test_seule_l_expansion_est_marquee_peu_discriminante():
    flags = {p["key"]: p["faible_discrimination"] for p in mapping.PHASES}
    assert flags == {"recovery": False, "expansion": True, "slowdown": False, "recession": False}


def test_la_limite_empirique_cite_les_deux_chiffres():
    assert "0,16 %" in mapping.LIMITE
    assert "2,3 %" in mapping.LIMITE
    assert "pas un signal" in mapping.LIMITE
    # Elle voyage dans l'export : c'est l'API qui l'affiche, pas une copie.
    assert mapping.describe()["limite"] == mapping.LIMITE


def test_normalisation_des_libelles_fournisseurs():
    # yfinance (Morningstar)
    assert mapping.normalize_sector("Consumer Cyclical") == "Consumer Discretionary"
    assert mapping.normalize_sector("Consumer Defensive") == "Consumer Staples"
    assert mapping.normalize_sector("Financial Services") == "Financials"
    assert mapping.normalize_sector("Healthcare") == "Health Care"
    assert mapping.normalize_sector("Basic Materials") == "Materials"
    assert mapping.normalize_sector("Technology") == "Information Technology"
    # déjà GICS : identité, insensible à la casse et aux espaces
    assert mapping.normalize_sector("  Real Estate ") == "Real Estate"
    # inconnu : None, jamais une devinette
    assert mapping.normalize_sector("Conglomerates") is None
    assert mapping.normalize_sector("") is None
    assert mapping.normalize_sector(None) is None


def test_tous_les_secteurs_observes_en_base_sont_reconnus():
    """Les neuf libellés que ticker_scores.sector portait le 2026-09-19."""
    observes = [
        "Technology", "Financial Services", "Communication Services",
        "Consumer Cyclical", "Healthcare", "Consumer Defensive",
        "Industrials", "Energy", "Basic Materials",
    ]
    assert all(mapping.normalize_sector(s) is not None for s in observes)


def test_la_contrainte_check_sql_liste_exactement_les_onze_secteurs():
    """La migration duplique la liste des noms GICS (c'est un standard, pas
    le mapping) : ce test empêche les deux copies de diverger."""
    sql = _MIGRATION.read_text(encoding="utf-8")
    bloc = re.search(r"secteur_gics IN \((.*?)\)\s*\);", sql, re.S)
    assert bloc, "contrainte societes_secteur_gics_check introuvable"
    en_sql = set(re.findall(r"'([^']+)'", bloc.group(1)))
    assert en_sql == set(mapping.SECTORS)


def test_la_contrainte_check_sql_liste_les_quatre_phases():
    sql = _MIGRATION.read_text(encoding="utf-8")
    bloc = re.search(r"phase IN \((.*?)\)", sql, re.S)
    assert bloc
    assert set(re.findall(r"'([^']+)'", bloc.group(1))) == set(mapping.PHASE_KEYS)


def test_export_json_est_le_describe(tmp_path):
    import json

    p = mapping.export(tmp_path / "m.json")
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["version"] == mapping.VERSION
    assert [s["key"] for s in data["sectors"]] == list(mapping.SECTORS)
    assert {s["key"]: s["nature"] for s in data["sectors"]}["Utilities"] == "defensif"
    assert {s["key"]: s["nature"] for s in data["sectors"]}["Energy"] == "cyclique"
    assert [p["key"] for p in data["phases"]] == list(mapping.PHASE_KEYS)
