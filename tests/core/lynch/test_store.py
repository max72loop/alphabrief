"""Écritures des catégories Lynch — contre la base MIROIR uniquement.

    ALPHABRIEF_DSN="dbname=alphabrief_mirror" pytest tests/core/lynch
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    "mirror" not in os.environ.get("ALPHABRIEF_DSN", ""),
    reason="écrit en base : ne tourne que sur la miroir (ALPHABRIEF_DSN=dbname=alphabrief_mirror)",
)

FAST = {"revenue_cagr_3y": 30, "net_income": 1}
SLOW = {"revenue_cagr_3y": 2, "net_income": 1}


@pytest.fixture(autouse=True)
def base_propre():
    from core.storage import db

    db.execute("DELETE FROM societes WHERE ticker LIKE %s", ["T\\_%"])
    yield
    db.execute("DELETE FROM societes WHERE ticker LIKE %s", ["T\\_%"])


def test_regles_posees_puis_recalculees():
    from core.lynch import store

    store.enregistrer("T_A", FAST, None)
    assert store.lire("T_A")["cle"] == "fast"
    assert store.lire("T_A")["source"] == store.SOURCE_REGLES
    store.enregistrer("T_A", SLOW, None)
    assert store.lire("T_A")["cle"] == "slow"


def test_correction_manuelle_jamais_ecrasee():
    from core.lynch import store

    store.enregistrer("T_B", FAST, None)
    store.declarer("T_B", "asset")
    store.enregistrer("T_B", SLOW, None)
    lu = store.lire("T_B")
    assert lu["cle"] == "asset" and lu["source"] == "manuel" and lu["regle"] is None


def test_retour_aux_regles():
    from core.lynch import store
    from core.storage import db

    # Le retour aux règles relit le secteur EN BASE (celui de la couche cycle).
    db.execute("INSERT INTO societes (ticker, secteur_gics, secteur_source, secteur_updated_at) "
               "VALUES ('T_C', 'Energy', 'test', now())")
    store.enregistrer("T_C", None, "Energy")
    store.declarer("T_C", "stalwart")
    lu = store.declarer("T_C", None)
    assert lu["cle"] == "cyclical" and lu["source"] == store.SOURCE_REGLES


def test_non_classable_efface_l_ancienne_proposition():
    from core.lynch import store

    store.enregistrer("T_D", FAST, None)
    store.enregistrer("T_D", {}, None)
    assert store.lire("T_D")["cle"] is None


def test_cle_inconnue_refusee():
    from core.lynch import store

    with pytest.raises(ValueError):
        store.declarer("T_E", "licorne")
