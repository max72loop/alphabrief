"""
Écrit et lit `societes.lynch_*` — la catégorie de Peter Lynch de chaque société.

Le contrat, inverse de celui du secteur (core/cycle/secteurs.py) :
- la catégorie PROPOSÉE par les règles est RECALCULÉE à chaque scoring — la
  croissance bouge, une société peut passer de « croissance rapide » à « valeur
  solide » ;
- une catégorie posée par Max (`lynch_source = 'manuel'`) n'est JAMAIS touchée
  par les règles. Seul `declarer(ticker, None)` la rend aux règles.

Clé = ticker NOTÉ (`listings.resolve`, GOOGL → GOOG), comme `these` et le secteur.

    python -m core.lynch.store                  # liste
    python -m core.lynch.store --backfill       # toutes les fiches notées
    python -m core.lynch.store --set TICKER CLE # correction de Max (manuel)
    python -m core.lynch.store --reset TICKER   # rend la société aux règles
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from core.lynch import categories as C
from core.scoring import listings
from core.storage import db

logger = logging.getLogger(__name__)

SOURCE_REGLES = f"regles:v{C.VERSION}"
SOURCE_MANUEL = "manuel"


def _scored(ticker: str) -> str:
    return (listings.resolve(ticker) or ticker).upper()


def enregistrer(ticker: str, financials: Optional[Dict[str, Any]], secteur_gics: Optional[str],
                nom: Optional[str] = None) -> Tuple[Optional[str], str]:
    """Pose la catégorie proposée par les règles, sauf si Max l'a corrigée.

    Renvoie (clé | None, règle). Une société non classable (croissance inconnue)
    garde sa ligne mais sa catégorie redevient NULL — pas de devinette, et pas
    d'ancienne valeur qui survivrait à une règle qui ne s'applique plus.
    Une erreur d'écriture REMONTE : le writer la loggue en ERROR et continue.
    """
    cle, regle = C.classer(financials, secteur_gics)
    now = datetime.now(timezone.utc)
    db.execute(
        "INSERT INTO societes (ticker, nom, lynch_categorie, lynch_source, lynch_regle, lynch_updated_at) "
        "VALUES (%s, %s, %s, %s, %s, %s) "
        "ON CONFLICT (ticker) DO UPDATE SET "
        "  nom = COALESCE(societes.nom, EXCLUDED.nom), "
        "  lynch_categorie = EXCLUDED.lynch_categorie, "
        "  lynch_source = EXCLUDED.lynch_source, "
        "  lynch_regle = EXCLUDED.lynch_regle, "
        "  lynch_updated_at = EXCLUDED.lynch_updated_at "
        # La correction de Max gagne toujours.
        "WHERE societes.lynch_source IS DISTINCT FROM %s",
        [_scored(ticker), nom, cle, SOURCE_REGLES if cle else None, regle, now if cle else None,
         SOURCE_MANUEL],
    )
    return cle, regle


def enregistrer_fiche(ticker: str, financials: Optional[Dict[str, Any]], nom: Optional[str] = None):
    """Appelé par `writer.write_score`, APRÈS le secteur : le secteur lu est celui
    de la base, donc une correction manuelle du secteur compte aussi ici."""
    row = db.query_one("SELECT secteur_gics FROM societes WHERE ticker = %s", [_scored(ticker)])
    return enregistrer(ticker, financials, (row or {}).get("secteur_gics"), nom=nom)


def _proposition(scored: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    row = db.query_one(
        "SELECT t.financials, s.secteur_gics FROM societes s "
        "LEFT JOIN ticker_scores t ON t.ticker = s.ticker WHERE s.ticker = %s",
        [scored],
    )
    if not row:
        return None, None
    return row["financials"], row["secteur_gics"]


def declarer(ticker: str, cle: Optional[str]) -> Dict[str, Any]:
    """Correction de Max. `cle` → posée en `manuel` ; None → rendue aux règles,
    recalculée tout de suite. Lève ValueError sur une clé inconnue."""
    scored = _scored(ticker)
    if cle is not None:
        if cle not in C.KEYS:
            raise ValueError(f"catégorie inconnue : {cle!r} (attendu : {', '.join(C.KEYS)})")
        db.execute(
            "INSERT INTO societes (ticker, lynch_categorie, lynch_source, lynch_regle, lynch_updated_at) "
            "VALUES (%s, %s, %s, NULL, %s) "
            "ON CONFLICT (ticker) DO UPDATE SET lynch_categorie = EXCLUDED.lynch_categorie, "
            "  lynch_source = EXCLUDED.lynch_source, lynch_regle = NULL, "
            "  lynch_updated_at = EXCLUDED.lynch_updated_at",
            [scored, cle, SOURCE_MANUEL, datetime.now(timezone.utc)],
        )
    else:
        # Tout effacer d'un coup : la contrainte de trace refuse une catégorie sans source.
        db.execute(
            "UPDATE societes SET lynch_categorie = NULL, lynch_source = NULL, lynch_regle = NULL, "
            "lynch_updated_at = NULL WHERE ticker = %s",
            [scored],
        )
        financials, secteur = _proposition(scored)
        enregistrer(scored, financials, secteur)
    return lire(scored)


def lire(ticker: str) -> Dict[str, Any]:
    row = db.query_one(
        "SELECT lynch_categorie, lynch_source, lynch_regle, lynch_updated_at FROM societes WHERE ticker = %s",
        [_scored(ticker)],
    ) or {}
    return {
        "cle": row.get("lynch_categorie"),
        "source": row.get("lynch_source"),
        "regle": row.get("lynch_regle"),
        "updated_at": row["lynch_updated_at"].isoformat() if row.get("lynch_updated_at") else None,
    }


def par_ticker() -> Dict[str, Dict[str, Any]]:
    """{ticker noté → {cle, source, regle}} pour toutes les sociétés classées."""
    rows = db.query(
        "SELECT ticker, lynch_categorie, lynch_source, lynch_regle FROM societes WHERE lynch_categorie IS NOT NULL"
    )
    return {r["ticker"].upper(): {"cle": r["lynch_categorie"], "source": r["lynch_source"],
                                  "regle": r["lynch_regle"]} for r in rows}


def backfill() -> Dict[str, int]:
    """Classe toutes les fiches notées depuis `ticker_scores` — après la migration,
    ou après un changement de règles. Les corrections manuelles restent."""
    rows = db.query(
        "SELECT t.ticker, t.company_name, t.financials, s.secteur_gics FROM ticker_scores t "
        "LEFT JOIN societes s ON s.ticker = t.ticker"
    )
    compte: Dict[str, int] = {}
    for r in rows:
        cle, _ = enregistrer(r["ticker"], r["financials"], r["secteur_gics"], nom=r["company_name"])
        compte[cle or "non_classee"] = compte.get(cle or "non_classee", 0) + 1
    return compte


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if "--backfill" in sys.argv:
        print(backfill())
    elif "--reset" in sys.argv or "--set" in sys.argv:
        # Appelé par pixel-office-api (PUT /api/alphabrief/societe) : la règle et
        # la validation restent ici, l'API ne les redéclare pas.
        import json
        flag = "--set" if "--set" in sys.argv else "--reset"
        args = sys.argv[sys.argv.index(flag) + 1:]
        if len(args) < (2 if flag == "--set" else 1):
            raise SystemExit("usage : --set TICKER CLE | --reset TICKER")
        try:
            lu = declarer(args[0], args[1] if flag == "--set" else None)
        except ValueError as e:
            print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
            raise SystemExit(2)
        print(json.dumps(lu, ensure_ascii=False))
    else:
        for t, v in sorted(par_ticker().items()):
            print(f"  {t:<10} {v['cle']:<11} {v['source']:<10} {v['regle'] or ''}")
