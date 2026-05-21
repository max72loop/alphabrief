"""
Upsert ticker scores into Supabase after each generate_card() call.
Uses urllib (stdlib only, no extra deps) so it works on the VPS without venv.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.request
import urllib.error
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
_SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _is_configured() -> bool:
    return bool(_SUPABASE_URL and _SUPABASE_KEY)


def _safe_float(v: Any) -> Optional[float]:
    try:
        return None if v is None else float(v)
    except Exception:
        return None


def _build_financials_summary(card: Dict[str, Any]) -> Dict[str, Any]:
    fin = card.get("financials", {})
    val = card.get("valuation", {})
    return {
        "revenue_cagr_3y": _safe_float(fin.get("revenue_cagr_3y")),
        "ebit_margin": _safe_float(fin.get("ebit_margin")),
        "gross_margin": _safe_float(fin.get("gross_margin")),
        "fcf_margin": _safe_float(fin.get("fcf_margin")),
        "roe": _safe_float(fin.get("roe")),
        "roic": _safe_float(fin.get("roic")),
        "net_debt_to_ebitda": _safe_float(fin.get("net_debt_to_ebitda")),
        "pe_ttm": _safe_float(val.get("pe_ttm")),
        "ev_ebitda_ttm": _safe_float(val.get("ev_ebitda_ttm")),
        "fcf_yield_ttm": _safe_float(val.get("fcf_yield_ttm")),
        "pb_ratio": _safe_float(val.get("pb_ratio")),
    }


def _build_market_summary(card: Dict[str, Any]) -> Dict[str, Any]:
    mkt = card.get("market", {})
    tech = card.get("technicals", {})
    return {
        "current_price": _safe_float(mkt.get("current_price")),
        "change_pct": _safe_float(mkt.get("change_pct")),
        "previous_close": _safe_float(mkt.get("previous_close")),
        "volume": _safe_float(mkt.get("volume")),
        "avg_volume_3m": _safe_float(mkt.get("avg_volume_3m")),
        "momentum_1m": _safe_float(mkt.get("momentum_1m")),
        "momentum_3m": _safe_float(mkt.get("momentum_3m")),
        "momentum_6m": _safe_float(mkt.get("momentum_6m")),
        "momentum_12m": _safe_float(mkt.get("momentum_12m")),
        "rsi_14": _safe_float(tech.get("rsi_14")),
        "sma_50": _safe_float(tech.get("sma_50")),
        "sma_200": _safe_float(tech.get("sma_200")),
        "macd_histogram": _safe_float(tech.get("macd_histogram")),
        "macd_line": _safe_float(tech.get("macd_line")),
        "beta": _safe_float(mkt.get("beta")),
        "dividend_yield": _safe_float(mkt.get("dividend_yield")),
        "fifty_two_week_low": _safe_float(mkt.get("fifty_two_week_low")),
        "fifty_two_week_high": _safe_float(mkt.get("fifty_two_week_high")),
        "analyst_target_mean": _safe_float(mkt.get("analyst_target_mean")),
        "analyst_target_low": _safe_float(mkt.get("analyst_target_low")),
        "analyst_target_high": _safe_float(mkt.get("analyst_target_high")),
        "analyst_count": mkt.get("analyst_count"),
        "analyst_recommendation": mkt.get("analyst_recommendation"),
    }


def _clean_importance_items(items: List[Any]) -> List[Dict[str, Any]]:
    """Garde uniquement les champs sérialisables des importance_items."""
    result = []
    for item in items or []:
        if isinstance(item, dict):
            result.append({
                "label": item.get("label", ""),
                "importance": _safe_float(item.get("importance")),
                "why": item.get("why", ""),
                "direction": item.get("direction", "neutral"),
            })
    return result[:10]


def upsert_ticker_score(card: Dict[str, Any]) -> None:
    """
    Upsert une ligne dans ticker_scores depuis une card générée.
    No-op silencieux si SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY non configurés.
    """
    if not _is_configured():
        logger.debug("Supabase non configuré — upsert ignoré")
        return

    scores = card.get("scores", {})
    total = scores.get("potential_score")
    if total is None:
        return

    ticker = card.get("identity", {}).get("ticker") or card.get("ticker", "")
    if not ticker:
        return

    identity = card.get("identity", {})
    snapshot = card.get("business_snapshot", {})
    importance_items = _clean_importance_items(scores.get("importance_ranked_items", []))

    row = {
        "ticker": ticker,
        "company_name": identity.get("name", ""),
        "sector": identity.get("sector", "") or "",
        "exchange": identity.get("exchange", "") or "",
        "currency": identity.get("currency", "") or "",
        "market_cap": _safe_float(identity.get("market_cap")),
        "one_liner": snapshot.get("one_liner", "") or "",
        "moat_tags": snapshot.get("moat_tags", []) or [],
        "score_total": total,
        "score_fundamentals": scores.get("score_fundamentals", total),
        "score_technicals": scores.get("score_technicals", total),
        "score_momentum": scores.get("score_momentum", total),
        "score_label": scores.get("score_label", ""),
        "importance_items": importance_items,
        "financials": _build_financials_summary(card),
        "market_data": _build_market_summary(card),
        "score_date": card.get("as_of") or date.today().isoformat(),
        "computed_at": datetime.now(timezone.utc).isoformat(),
    }

    url = f"{_SUPABASE_URL}/rest/v1/ticker_scores"
    payload = json.dumps([row]).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "apikey": _SUPABASE_KEY,
            "Authorization": f"Bearer {_SUPABASE_KEY}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            status = resp.status
            if status in (200, 201, 204):
                logger.info(f"Supabase upsert OK — {ticker} score={total}")
            else:
                body = resp.read().decode("utf-8", errors="replace")
                logger.warning(f"Supabase upsert {status} — {ticker}: {body}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error(f"Supabase upsert HTTP {e.code} — {ticker}: {body}")
    except Exception as e:
        logger.error(f"Supabase upsert failed — {ticker}: {e}")
