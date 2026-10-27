"""Écritures de la couche cycle — contre la base MIROIR uniquement.

Sautés si `ALPHABRIEF_DSN` ne vise pas explicitement la miroir : ces tests
écrivent (`societes`, `cycle_phase_declarations`) et la règle du dépôt est
sans exception — autonomie totale sur la miroir, nulle sur `alphabrief`.

    ALPHABRIEF_DSN="dbname=alphabrief_mirror" pytest tests/core/cycle
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    "mirror" not in os.environ.get("ALPHABRIEF_DSN", ""),
    reason="écrit en base : ne tourne que sur la miroir (ALPHABRIEF_DSN=dbname=alphabrief_mirror)",
)


@pytest.fixture(autouse=True)
def base_propre():
    from core.storage import db

    db.execute("DELETE FROM societes WHERE ticker LIKE %s", ["T\\_%"])
    db.execute("DELETE FROM cycle_phase_declarations")
    yield
    db.execute("DELETE FROM societes WHERE ticker LIKE %s", ["T\\_%"])
    db.execute("DELETE FROM cycle_phase_declarations")


def _card(sector, name="Société Test", source="yf-direct"):
    return {"identity": {"sector": sector, "name": name}, "sources": [{"name": source}]}


def test_pose_le_secteur_normalise_avec_source_et_date():
    from core.cycle import secteurs
    from core.storage import db

    assert secteurs.enregistrer("T_A", _card("Consumer Cyclical")) == "Consumer Discretionary"
    row = db.query_one("SELECT * FROM societes WHERE ticker = 'T_A'")
    assert row["secteur_gics"] == "Consumer Discretionary"
    assert row["secteur_source"] == "yf-direct"
    assert row["secteur_updated_at"] is not None
    assert row["nom"] == "Société Test"


def test_ne_remplace_jamais_un_secteur_deja_pose():
    from core.cycle import secteurs
    from core.storage import db

    secteurs.enregistrer("T_B", _card("Healthcare", source="yf-direct"))
    premiere = db.query_one("SELECT secteur_updated_at FROM societes WHERE ticker = 'T_B'")
    # Un scoring ultérieur avec un autre libellé et une autre source : ignoré.
    secteurs.enregistrer("T_B", _card("Technology", source="fmp"))
    row = db.query_one("SELECT * FROM societes WHERE ticker = 'T_B'")
    assert row["secteur_gics"] == "Health Care"
    assert row["secteur_source"] == "yf-direct"
    assert row["secteur_updated_at"] == premiere["secteur_updated_at"]


def test_une_these_existante_n_est_pas_touchee():
    from core.cycle import secteurs
    from core.storage import db

    db.execute("INSERT INTO societes (ticker, nom, these) VALUES ('T_C', 'Nom saisi', 'ma thèse')")
    secteurs.enregistrer("T_C", _card("Energy", name="Nom fournisseur"))
    row = db.query_one("SELECT * FROM societes WHERE ticker = 'T_C'")
    assert row["these"] == "ma thèse"
    assert row["nom"] == "Nom saisi"          # le nom existant gagne aussi
    assert row["secteur_gics"] == "Energy"


def test_secteur_inconnu_n_ecrit_rien():
    from core.cycle import secteurs
    from core.storage import db

    assert secteurs.enregistrer("T_D", _card("Conglomerates")) is None
    assert db.query_one("SELECT 1 FROM societes WHERE ticker = 'T_D'") is None


def test_par_ticker_ne_liste_que_les_classees():
    from core.cycle import secteurs
    from core.storage import db

    db.execute("INSERT INTO societes (ticker) VALUES ('T_E')")
    secteurs.enregistrer("T_F", _card("Utilities"))
    tickers = secteurs.par_ticker()
    assert tickers.get("T_F") == "Utilities"
    assert "T_E" not in tickers


def test_declaration_datee_la_derniere_fait_foi():
    from core.cycle import phase

    assert phase.declaree() is None
    assert phase.ligne_rappel() == "Phase du cycle : aucune déclarée"

    d1 = phase.declarer("recovery")
    assert d1["phase"] == "recovery" and d1["label"] == "Reprise"
    assert d1["declared_at"] is not None

    d2 = phase.declarer("slowdown")
    assert phase.declaree()["phase"] == "slowdown"
    assert d2["declared_at"] >= d1["declared_at"]
    assert phase.ligne_rappel().startswith("Phase du cycle : Fin de cycle, déclarée le ")


def test_declaration_hors_modele_refusee_avant_la_base():
    from core.cycle import phase

    with pytest.raises(ValueError):
        phase.declarer("boom")
    assert phase.declaree() is None
