"""
Writer Supabase pour AlphaBrief.
UPSERT dans ticker_scores (schéma existant), INSERT dans score_history.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone
from typing import Any, Dict, Optional

from supabase import create_client, Client

from config import Config

logger = logging.getLogger(__name__)

_client: Optional[Client] = None


def _get_client() -> Optional[Client]:
    global _client
    if _client is not None:
        return _client
    if not Config.SUPABASE_URL or not Config.SUPABASE_KEY:
        logger.warning("Supabase credentials not configured — writer disabled")
        return None
    _client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
    return _client


def write_score(ticker: str, card: Dict[str, Any]) -> bool:
    """
    Upsert le score dans ticker_scores et insert dans score_history.
    Adapté au schéma existant de la table ticker_scores.
    Retourne True si succès, False sinon.
    """
    client = _get_client()
    if client is None:
        return False

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
        logger.warning(f"Supabase skip {ticker}: no potential_score")
        return False

    now = datetime.now(timezone.utc).isoformat()
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

    # Merge market data
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

    try:
        row = {
            "ticker": ticker.upper(),
            "score_total": potential,
            "score_fundamentals": fundamentals_sc,
            "score_technicals": technicals_sc,
            "score_momentum": momentum_sc,
            "score_date": date.today().isoformat(),
            "computed_at": now,
            "market_cap": identity.get("market_cap"),
            "one_liner": business.get("one_liner", ""),
            "moat_tags": business.get("moat_tags", []),
            "score_label": scores.get("score_label", ""),
            "importance_items": importance,
            "financials": fin_merged,
            "market_data": market_data,
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
        client.table("ticker_scores").upsert(row, on_conflict="ticker").execute()
        logger.info(f"Supabase upsert ticker_scores: {ticker} = {potential}/100")
    except Exception as e:
        logger.error(f"Supabase upsert ticker_scores failed for {ticker}: {e}")
        return False

    try:
        history_row = {
            "ticker": ticker.upper(),
            "score": potential,
            "confidence": confidence or 0,
            "recorded_at": now,
        }
        client.table("score_history").insert(history_row).execute()
        logger.info(f"Supabase insert score_history: {ticker}")
    except Exception as e:
        # score_history may not exist yet, log but don't fail
        logger.warning(f"Supabase insert score_history skipped for {ticker}: {e}")

    return True


def write_alert(ticker: str, alert_type: str, prev_score: Optional[int],
                new_score: int, message: str) -> bool:
    """Insert une alerte dans Supabase."""
    client = _get_client()
    if client is None:
        return False

    try:
        row = {
            "ticker": ticker.upper(),
            "alert_type": alert_type,
            "prev_score": prev_score,
            "new_score": new_score,
            "message": message,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        client.table("alerts").insert(row).execute()
        logger.info(f"Supabase alert: {alert_type} for {ticker}")
        return True
    except Exception as e:
        logger.warning(f"Supabase alert insert skipped for {ticker}: {e}")
        return False
