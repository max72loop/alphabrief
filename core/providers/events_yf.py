"""
Récupère les événements d'un ticker depuis yfinance et les upsert dans
la table `ticker_events` du Postgres local.

Types d'events stockés :
- 'earnings' : dates de publication (passées + à venir)
- 'dividend' : prochain ex-dividend date si dispo
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any

import yfinance as yf

from core.storage import db

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


def _upsert_events(events: list[dict[str, Any]]) -> bool:
    """Upsert sur (ticker, event_date, kind) — voir la contrainte du même nom
    dans db/schema.sql, qui est ce qui rend ce ON CONFLICT possible."""
    if not events:
        return False
    try:
        with db.connection() as conn:
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO ticker_events (ticker, event_date, label, kind, source) "
                    "VALUES (%(ticker)s, %(event_date)s, %(label)s, %(kind)s, %(source)s) "
                    "ON CONFLICT (ticker, event_date, kind) DO UPDATE "
                    "   SET label = EXCLUDED.label, source = EXCLUDED.source",
                    events,
                )
        return True
    except Exception as e:
        logger.warning(f"upsert ticker_events failed: {e}")
        return False


def sync_events_for(ticker: str) -> int:
    """Sync les événements d'un ticker. Renvoie le nombre d'events écrits."""
    upper = ticker.upper()
    payload: list[dict[str, Any]] = []

    for ev in _fetch_earnings_dates(upper, limit=8):
        payload.append({"ticker": upper, **ev})

    div = _fetch_next_dividend(upper)
    if div:
        payload.append({"ticker": upper, **div})

    if not payload:
        return 0

    ok = _upsert_events(payload)
    if ok:
        logger.info(f"  ↳ {upper}: synchronisé {len(payload)} événement(s)")
    return len(payload) if ok else 0
