"""
Writer AlphaBrief — Postgres local.
UPSERT dans ticker_scores, INSERT dans score_history.

Remplace core/storage/supabase_writer.py (client Supabase via HTTP). La
logique métier est inchangée ; seule la persistance a changé de nature.

`write_alert()` n'est pas repris : la fonction n'avait aucun appelant dans tout
le dépôt (vérifié par grep) et écrivait dans une table `alerts` qui n'a jamais
existé côté base. Elle échouait donc silencieusement à chaque appel qui n'a
jamais eu lieu. La fonctionnalité d'alertes se tranche au lot 4 — la recréer
ici reviendrait à réimplémenter du code mort.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict

from psycopg.types.json import Jsonb

from core.storage import db

logger = logging.getLogger(__name__)


def write_score(ticker: str, card: Dict[str, Any]) -> bool:
    """
    Upsert le score dans ticker_scores et insert dans score_history.
    Retourne True si succès, False sinon.
    """
    scores = card.get("scores", {})
    potential = scores.get("potential_score")
    confidence = scores.get("confidence_score")
    # Sous-scores 50/25/25 calculés par compute_potential_score. Fallback sur le
    # total pour les anciennes cards sérialisées avant l'introduction du breakdown
    # (évite d'écrire des null qui casseraient le front). Nommés _sc pour ne pas
    # entrer en collision avec `technicals` (dict) et `financials` (dict) plus bas.
    fundamentals_sc = scores.get("fundamentals_score")
    technicals_sc = scores.get("technicals_score")
    momentum_sc = scores.get("momentum_score")
    if fundamentals_sc is None:
        fundamentals_sc = potential
    if technicals_sc is None:
        technicals_sc = potential
    if momentum_sc is None:
        momentum_sc = potential

    if potential is None:
        logger.warning(f"skip {ticker}: no potential_score")
        return False

    now = datetime.now(timezone.utc)
    identity = card.get("identity", {})
    market = card.get("market", {})
    financials = card.get("financials", {})
    valuation = card.get("valuation", {})
    technicals = card.get("technicals", {})
    business = card.get("business_snapshot", {})
    importance = scores.get("importance_ranked_items", [])

    # Merge financials + valuation into one dict for the financials JSONB column
    fin_merged = {}
    fin_merged.update(financials)
    fin_merged.update(valuation)

    market_data = {
        "beta": market.get("beta"),
        "rsi_14": technicals.get("rsi_14"),
        "sma_50": technicals.get("sma_50"),
        "sma_200": technicals.get("sma_200"),
        "momentum_3m": market.get("momentum_3m"),
        "momentum_12m": market.get("momentum_12m"),
        "analyst_target_mean": market.get("analyst_target_mean"),
        "analyst_recommendation": market.get("analyst_recommendation"),
    }

    row: Dict[str, Any] = {
        "ticker": ticker.upper(),
        "score_total": potential,
        "score_fundamentals": fundamentals_sc,
        "score_technicals": technicals_sc,
        "score_momentum": momentum_sc,
        "score_date": date.today(),
        "computed_at": now,
        "market_cap": identity.get("market_cap"),
        "one_liner": business.get("one_liner", ""),
        "moat_tags": Jsonb(business.get("moat_tags", [])),
        "score_label": scores.get("score_label", ""),
        "importance_items": Jsonb(importance),
        "financials": Jsonb(fin_merged),
        "market_data": Jsonb(market_data),
    }
    # Champs d'identité : on ne les inclut que si FMP a effectivement renvoyé
    # une valeur. Sinon l'upsert écraserait des données déjà correctes
    # (ex. un backfill yfinance) avec des chaînes vides quand FMP est en
    # quota ou que /profile n'a rien renvoyé pour ce ticker.
    for col, key in (("company_name", "name"), ("sector", "sector"),
                     ("exchange", "exchange"), ("currency", "currency")):
        val = identity.get(key)
        if val:
            row[col] = val

    try:
        cols = list(row.keys())
        collist = ", ".join(cols)
        marks = ", ".join(["%s"] * len(cols))
        # Les colonnes absentes de l'upsert gardent leur valeur : c'est ce qui
        # protège un backfill yfinance quand FMP ne renvoie rien.
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != "ticker")
        db.execute(
            f"INSERT INTO ticker_scores ({collist}) VALUES ({marks}) "
            f"ON CONFLICT (ticker) DO UPDATE SET {updates}",
            list(row.values()),
        )
        logger.info(f"upsert ticker_scores: {ticker} = {potential}/100")
    except Exception as e:
        logger.error(f"upsert ticker_scores failed for {ticker}: {e}")
        return False

    try:
        # La colonne est `scored_at`, pas `recorded_at`. L'ancienne migration
        # déclarait `recorded_at` et se trompait : la table déployée utilisait
        # `scored_at`, ce que lisait déjà le frontend. Chaque insert échouait
        # en PGRST204 depuis toujours, avalé par le except ci-dessous.
        db.execute(
            "INSERT INTO score_history (ticker, score, confidence, scored_at) "
            "VALUES (%s, %s, %s, %s)",
            [ticker.upper(), potential, confidence or 0, now],
        )
        logger.info(f"insert score_history: {ticker}")
    except Exception as e:
        # On continue — l'historique est secondaire face au score courant —
        # mais en ERROR, pas en WARNING : un historique qui ne s'écrit plus
        # ne doit pas se remarquer six mois plus tard sur un graphe plat.
        logger.error(f"insert score_history ECHEC pour {ticker}: {e}")

    return True
