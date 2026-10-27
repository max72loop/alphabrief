"""
Alimente `societes.secteur_gics` depuis l'identité de la fiche.

Le contrat : on POSE un secteur, on ne l'ÉCRASE jamais. Une valeur déjà en
base — qu'elle vienne d'un scoring précédent ou d'une correction manuelle
(`secteur_source = 'manuel'`) — reste. C'est la même règle que l'identité dans
`core/storage/writer.py` : un scoring dégradé ne doit pas effacer ce qu'un
précédent savait.

La source réelle est celle de la fiche (`card["sources"][0]["name"]`) :
`fmp`, `yf-direct` ou `fmp+yf`. FMP est hors service depuis le 2026-09-02
(voir CLAUDE.md, Gotchas) — en pratique c'est yfinance qui remplit, et la
colonne `secteur_source` le dit plutôt que de le laisser croire.

Clé = ticker NOTÉ (GOOGL → GOOG), comme `these` : un secteur par société,
jamais un par cotation.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.cycle.mapping import normalize_sector
from core.scoring import listings
from core.storage import db

logger = logging.getLogger(__name__)


def _source_de(card: Dict[str, Any]) -> str:
    sources = card.get("sources") or []
    if sources and isinstance(sources[0], dict) and sources[0].get("name"):
        return str(sources[0]["name"])
    return "yfinance"


def enregistrer(ticker: str, card: Dict[str, Any]) -> Optional[str]:
    """Pose le secteur GICS de `ticker` s'il est encore inconnu en base.

    Renvoie le secteur normalisé, ou None si la fiche n'en porte pas de
    reconnaissable — auquel cas rien n'est écrit (pas de ligne `societes`
    créée pour rien, et surtout pas de devinette).

    Une erreur d'écriture REMONTE : l'appelant décide (le writer la loggue en
    ERROR et continue, le score étant l'essentiel). Pas d'except silencieux.
    """
    identity = card.get("identity") or {}
    secteur = normalize_sector(identity.get("sector"))
    if secteur is None:
        return None

    scored = (listings.resolve(ticker) or ticker).upper()
    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO societes (ticker, nom, secteur_gics, secteur_source, secteur_updated_at) "
        "VALUES (%s, %s, %s, %s, %s) "
        "ON CONFLICT (ticker) DO UPDATE SET "
        "  nom = COALESCE(societes.nom, EXCLUDED.nom), "
        # Une valeur existante gagne toujours — COALESCE dans ce sens-là.
        "  secteur_gics = COALESCE(societes.secteur_gics, EXCLUDED.secteur_gics), "
        "  secteur_source = CASE WHEN societes.secteur_gics IS NULL "
        "                        THEN EXCLUDED.secteur_source ELSE societes.secteur_source END, "
        "  secteur_updated_at = CASE WHEN societes.secteur_gics IS NULL "
        "                            THEN EXCLUDED.secteur_updated_at ELSE societes.secteur_updated_at END",
        [scored, identity.get("name") or None, secteur, _source_de(card), now],
    )
    return secteur


def par_ticker() -> Dict[str, str]:
    """{ticker noté → secteur GICS} pour toutes les sociétés classées."""
    rows = db.query("SELECT ticker, secteur_gics FROM societes WHERE secteur_gics IS NOT NULL")
    return {r["ticker"].upper(): r["secteur_gics"] for r in rows}


def backfill_depuis_ticker_scores() -> Dict[str, int]:
    """Reprend le secteur déjà connu de `ticker_scores.sector` pour toutes les
    fiches notées — une fois, après la migration. Même règle : ne pose que
    ce qui manque.

    Renvoie {"traites": n, "inconnus": m} — « traité » = un secteur reconnu a
    été proposé à la base, qui l'a posé s'il manquait. Les libellés non
    reconnus sont loggués en WARNING avec le ticker, pour être ajoutés aux
    alias s'ils sont légitimes (jamais devinés ici).
    """
    rows = db.query(
        "SELECT ticker, company_name, sector FROM ticker_scores WHERE sector IS NOT NULL AND sector <> ''"
    )
    traites = 0
    inconnus = 0
    for r in rows:
        secteur = normalize_sector(r["sector"])
        if secteur is None:
            inconnus += 1
            logger.warning(f"secteur non reconnu pour {r['ticker']} : {r['sector']!r}")
            continue
        card = {
            "identity": {"sector": r["sector"], "name": r["company_name"]},
            "sources": [{"name": "backfill:ticker_scores"}],
        }
        if enregistrer(r["ticker"], card):
            traites += 1
    return {"traites": traites, "inconnus": inconnus}


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if "--backfill" in sys.argv:
        print(backfill_depuis_ticker_scores())
    else:
        for t, s in sorted(par_ticker().items()):
            print(f"  {t:<10} {s}")
