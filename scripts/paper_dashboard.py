#!/usr/bin/env python3
"""Expose le state paper trading (TOP10) en JSON sur stdout, pour consumption
par pixel-office-api (qui le sert au dashboard Pixel Office).

Format de sortie :
{
  "portfolio": {"id", "name", "initial_capital", "started_at"},
  "current": {
    "nav": float,                 # NAV mark-to-market live (FMP)
    "nav_stored": float,          # derniere NAV ecrite en DB (peut etre stale le lundi)
    "perf_pct": float,            # (nav / initial - 1) * 100
    "perf_stored_pct": float,
    "cash": float,
    "long_value": float,
    "fees_paid": float,
    "n_positions": int,
    "stale_warning": bool,        # True si nav_stored != nav (typiquement lundi pre-22h-UTC)
  },
  "positions": [
    {"ticker", "company_name", "shares", "entry_price", "live_price",
     "notional_at_entry", "notional_live", "weight_pct", "pnl_usd", "pnl_pct",
     "entry_date"}
  ],
  "nav_history": [{"date", "nav"}, ...],     # 30 derniers jours
  "fetched_at": ISO timestamp
}

Sur erreur (Supabase down, FMP rate limit, etc.) : exit 1 + stderr message.
"""
from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Optional

# Reuse paper_mvp's supabase + fmp init (DRY)
sys.path.insert(0, "/root/agents/alphabrief")
from paper_mvp import _supabase, _fetch_quote, INITIAL_CAPITAL


PORTFOLIO_NAME = "TOP10"
HISTORY_DAYS = 30


def _err(msg: str, code: int = 1) -> None:
    print(json.dumps({"error": msg}), file=sys.stderr)
    sys.exit(code)


def build() -> dict:
    sb = _supabase()

    # 1. Portfolio
    portfolios = sb.table("paper_portfolios").select("*").eq("name", PORTFOLIO_NAME).limit(1).execute()
    if not portfolios.data:
        _err(f"portfolio '{PORTFOLIO_NAME}' not found")
    portfolio = portfolios.data[0]
    pid = portfolio["id"]

    # 2. Positions courantes
    pos_rows = (sb.table("paper_positions").select("*")
                .eq("portfolio_id", pid).execute()).data

    # 3. NAV history (HISTORY_DAYS derniers jours, tri date asc pour la courbe)
    nav_rows = (sb.table("paper_nav_history").select("date, nav, cash_balance")
                .eq("portfolio_id", pid)
                .order("date", desc=True).limit(HISTORY_DAYS).execute()).data
    nav_rows.reverse()  # asc pour le sparkline
    nav_history = [{"date": r["date"], "nav": float(r["nav"])} for r in nav_rows]

    # Derniere NAV stockee (avant mark-to-market)
    nav_stored = float(nav_rows[-1]["nav"]) if nav_rows else float(portfolio["initial_capital"])
    cash_stored = float(nav_rows[-1]["cash_balance"]) if nav_rows else float(portfolio["initial_capital"])

    # 4a. Noms d'entreprise via ticker_scores (best-effort, position vide si absent)
    tickers = [p["ticker"] for p in pos_rows]
    name_map: dict[str, Optional[str]] = {}
    if tickers:
        try:
            name_rows = (sb.table("ticker_scores").select("ticker, company_name")
                         .in_("ticker", tickers).execute()).data
            name_map = {r["ticker"]: r.get("company_name") for r in name_rows}
        except Exception:
            name_map = {}

    # 4b. Mark-to-market live via FMP pour chaque position
    positions_out = []
    long_value_live = 0.0
    long_value_entry = 0.0
    fmp_failures = 0
    for p in pos_rows:
        tk = p["ticker"]
        shares = float(p["shares"])
        entry = float(p["entry_price"])
        live = _fetch_quote(tk)
        if live is None:
            fmp_failures += 1
            live_used = entry
        else:
            live_used = live
        notional_entry = shares * entry
        notional_live = shares * live_used
        pnl_usd = notional_live - notional_entry
        pnl_pct = (live_used / entry - 1) * 100 if entry > 0 else 0.0
        long_value_live += notional_live
        long_value_entry += notional_entry
        positions_out.append({
            "ticker": tk,
            "company_name": name_map.get(tk),
            "shares": round(shares, 4),
            "entry_price": round(entry, 2),
            "live_price": round(live, 2) if live is not None else None,
            "notional_at_entry": round(notional_entry, 2),
            "notional_live": round(notional_live, 2),
            "pnl_usd": round(pnl_usd, 2),
            "pnl_pct": round(pnl_pct, 2),
            "entry_date": p.get("entry_date"),
        })
    # Tri par notional desc (plus grosse position en haut)
    positions_out.sort(key=lambda r: r["notional_live"], reverse=True)

    # 5. Fees cumules (approximation : count rebalances * 9.99, ou somme exacte si dispo)
    fees_rows = (sb.table("paper_rebalances").select("fees")
                 .eq("portfolio_id", pid).execute()).data
    fees_paid = round(sum(float(r.get("fees", 0) or 0) for r in fees_rows), 2)

    nav_live = round(long_value_live + cash_stored, 2)
    # Poids = part de la NAV totale (long_value + cash), pas seulement de l'equity
    for r in positions_out:
        r["weight_pct"] = round(r["notional_live"] / nav_live * 100, 2) if nav_live > 0 else 0.0
    perf_pct = round((nav_live / INITIAL_CAPITAL - 1) * 100, 4)
    perf_stored_pct = round((nav_stored / INITIAL_CAPITAL - 1) * 100, 4)
    stale = abs(nav_live - nav_stored) > 1.0  # tolerance $1 d'arrondi

    return {
        "portfolio": {
            "id": pid,
            "name": portfolio["name"],
            "initial_capital": float(portfolio["initial_capital"]),
            "started_at": portfolio.get("started_at"),
            "strategy": portfolio.get("strategy"),
        },
        "current": {
            "nav": nav_live,
            "nav_stored": round(nav_stored, 2),
            "perf_pct": perf_pct,
            "perf_stored_pct": perf_stored_pct,
            "cash": round(cash_stored, 2),
            "long_value": round(long_value_live, 2),
            "long_value_at_entry": round(long_value_entry, 2),
            "fees_paid": fees_paid,
            "n_positions": len(positions_out),
            "stale_warning": stale,
            "fmp_failures": fmp_failures,
        },
        "positions": positions_out,
        "nav_history": nav_history,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    try:
        out = build()
        print(json.dumps(out, default=str))
    except Exception as e:
        _err(f"{type(e).__name__}: {e}")
