"""
Récupère les événements d'un ticker depuis yfinance et les upsert dans
la table Supabase `ticker_events`.

Types d'events stockés :
- 'earnings' : dates de publication (passées + à venir)
- 'dividend' : prochain ex-dividend date si dispo
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any

import yfinance as yf

logger = logging.getLogger(__name__)


def _earnings_label(d: date) -> str:
    """Renvoie un libellé court type 'Q2 EARNINGS'."""
    quarter = (d.month - 1) // 3 + 1
    return f"Q{quarter} EARNINGS"


def _fetch_earnings_dates(ticker: str, limit: int = 6) -> list[dict[str, Any]]:
    """
    Renvoie une liste d'événements earnings : les `limit` plus récents
    (passés ou à venir). Format : [{event_date, label, kind}, ...]
    """
    try:
        t = yf.Ticker(ticker)
        df = t.earnings_dates  # DataFrame indexé par date, ou None
    except Exception as e:
        logger.debug(f"earnings_dates {ticker} failed: {e}")
        return []

    if df is None or len(df) == 0:
        return []

    events: list[dict[str, Any]] = []
    # df.index contient des Timestamps tz-aware
    for ts in df.index[:limit]:
        try:
            d = ts.date() if hasattr(ts, "date") else date.fromisoformat(str(ts)[:10])
            events.append({
                "event_date": d.isoformat(),
                "label": _earnings_label(d),
                "kind": "earnings",
                "source": "yfinance",
            })
        except Exception:
            continue
    return events


def _fetch_next_dividend(ticker: str) -> dict[str, Any] | None:
    """Renvoie le prochain ex-dividend date si dispo."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        ts = info.get("exDividendDate")
        if not ts:
            return None
        d = datetime.fromtimestamp(int(ts), tz=timezone.utc).date()
        # Garde uniquement le futur (les passés viennent du flux earnings)
        if d < date.today() - timedelta(days=2):
            return None
        return {
            "event_date": d.isoformat(),
            "label": "DIVIDENDE",
            "kind": "dividend",
            "source": "yfinance",
        }
    except Exception as e:
        logger.debug(f"dividend {ticker} failed: {e}")
        return None


def _sb_upsert(url: str, key: str, events: list[dict[str, Any]]) -> bool:
    if not url or not key or not events:
        return False
    endpoint = f"{url.rstrip('/')}/rest/v1/ticker_events?on_conflict=ticker,event_date,kind"
    body = json.dumps(events).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body, method="POST", headers={
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        logger.warning(f"Supabase upsert ticker_events → HTTP {e.code}: {e.read()[:200]}")
        return False
    except Exception as e:
        logger.warning(f"Supabase upsert ticker_events failed: {e}")
        return False


def sync_events_for(ticker: str) -> int:
    """
    Sync les événements d'un ticker. Renvoie le nombre d'events envoyés.
    No-op si SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY absents.
    """
    sb_url = os.environ.get("SUPABASE_URL", "")
    sb_key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_KEY", "")
    )
    if not sb_url or not sb_key:
        return 0

    upper = ticker.upper()
    payload: list[dict[str, Any]] = []

    for ev in _fetch_earnings_dates(upper, limit=8):
        payload.append({"ticker": upper, **ev})

    div = _fetch_next_dividend(upper)
    if div:
        payload.append({"ticker": upper, **div})

    if not payload:
        return 0

    ok = _sb_upsert(sb_url, sb_key, payload)
    if ok:
        logger.info(f"  ↳ {upper}: synchronisé {len(payload)} événement(s)")
    return len(payload) if ok else 0
