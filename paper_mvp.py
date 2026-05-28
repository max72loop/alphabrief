"""AlphaBrief Paper Trading MVP — top 10 by score, équipondéré, hebdo.

Lives at /root/agents/alphabrief/paper_mvp.py (PM2 active scheduler).
The /root/alphabrief/core/paper_portfolio/ Phase 3B skeletons are frozen —
see /root/alphabrief/core/paper_portfolio/README.md.

LONG only, équipondéré 10% NAV, fees 10 bps per leg, no slippage, no SL,
no hash-chain (placeholder row_hash to satisfy DB UNIQUE constraint), no
corporate actions, no metrics.

Tables Supabase réutilisées : paper_portfolios, paper_positions (mutable),
paper_rebalances/paper_nav_history/paper_missed_rebalances (append-only).
"""
from __future__ import annotations

import hashlib
import os
import sys
from datetime import date
from typing import Optional

sys.path.insert(0, "/root/alphabrief")
sys.path.insert(0, "/root")

from alfred.shared.logger import get_logger

logger = get_logger("paper_mvp")

PORTFOLIO_NAME = "TOP10"  # contraint par migration CHECK (TOP10|BOTTOM10|LONG_SHORT|SPY_BENCHMARK)
PORTFOLIO_STRATEGY = "MVP — Top 10 by score_total, équipondéré, rebalance hebdo lundi 14h UTC, fees 10bps"
INITIAL_CAPITAL = float(os.environ.get("PAPER_MVP_INITIAL_CAPITAL", "100000"))
TARGET_COUNT = 10
SCORE_PREFERENCE_THRESHOLD = 75
FEES_BPS = 10

_supabase_client = None


def _supabase():
    global _supabase_client
    if _supabase_client is None:
        from supabase import create_client
        from config import Config
        _supabase_client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
    return _supabase_client


def _placeholder_row_hash(portfolio_id: int, d: str, ticker: str, action: str, shares: float) -> str:
    return hashlib.sha256(f"{portfolio_id}|{d}|{ticker}|{action}|{shares:.4f}".encode()).hexdigest()


def _fetch_quote(ticker: str) -> Optional[float]:
    """Returns current price via yfinance, or None on failure.

    yfinance, pas FMP : le plan FMP est saturé en quota (429 permanent),
    et le paper trading n'a besoin que d'un last_price simple.
    """
    import yfinance as yf
    try:
        price = getattr(yf.Ticker(ticker).fast_info, "last_price", None)
        return float(price) if price and price > 0 else None
    except Exception as e:
        logger.warning(f"yfinance quote {ticker} failed: {e}")
        return None


def bootstrap_portfolio() -> int:
    """Idempotent: creates MVP_TOP10 row on first run, returns its id."""
    sb = _supabase()
    existing = sb.table("paper_portfolios").select("id, started_at").eq("name", PORTFOLIO_NAME).execute()
    if existing.data:
        pid = existing.data[0]["id"]
        if existing.data[0].get("started_at") is None:
            sb.table("paper_portfolios").update({"started_at": date.today().isoformat()}).eq("id", pid).execute()
        return pid
    inserted = sb.table("paper_portfolios").insert({
        "name": PORTFOLIO_NAME,
        "strategy": PORTFOLIO_STRATEGY,
        "initial_capital": INITIAL_CAPITAL,
        "started_at": date.today().isoformat(),
    }).execute()
    pid = inserted.data[0]["id"]
    logger.info(f"paper_portfolios[{pid}] = {PORTFOLIO_NAME} bootstrapped, capital ${INITIAL_CAPITAL:.0f}")
    return pid


def _load_top_n_scores(n: int = TARGET_COUNT) -> list[dict]:
    res = (_supabase().table("ticker_scores")
           .select("ticker, score_total").order("score_total", desc=True).limit(n).execute())
    rows = res.data or []
    high = [r for r in rows if (r.get("score_total") or 0) >= SCORE_PREFERENCE_THRESHOLD]
    if len(high) < n:
        logger.warning(f"Univers réduit: {len(high)}/{n} ticker(s) ≥ score {SCORE_PREFERENCE_THRESHOLD}, on prend les meilleurs")
    return [{"ticker": r["ticker"], "score": r.get("score_total")} for r in rows]


def _load_open_positions(portfolio_id: int) -> dict[str, dict]:
    res = _supabase().table("paper_positions").select("*").eq("portfolio_id", portfolio_id).execute()
    return {r["ticker"]: r for r in (res.data or [])}


def _last_nav(portfolio_id: int) -> tuple[float, float]:
    res = (_supabase().table("paper_nav_history").select("nav, cash_balance")
           .eq("portfolio_id", portfolio_id).order("date", desc=True).limit(1).execute())
    if res.data:
        return float(res.data[0]["nav"]), float(res.data[0]["cash_balance"])
    return INITIAL_CAPITAL, INITIAL_CAPITAL


def _compute_cash(portfolio_id: int) -> float:
    """Cash = initial_capital − Σ(BUY cost) + Σ(SELL net), dérivé de paper_rebalances.

    Source de vérité unique. paper_nav_history.cash_balance peut diverger
    temporairement (NAV daily écrite avant un rebalance du même jour).
    """
    sb = _supabase()
    pf = sb.table("paper_portfolios").select("initial_capital").eq("id", portfolio_id).execute().data
    cash = float(pf[0]["initial_capital"]) if pf else INITIAL_CAPITAL
    trades = (sb.table("paper_rebalances").select("action, shares, price, fees")
                .eq("portfolio_id", portfolio_id).execute().data) or []
    for t in trades:
        gross = float(t["shares"]) * float(t["price"])
        fees = float(t["fees"])
        if t["action"] == "BUY":
            cash -= gross + fees
        elif t["action"] == "SELL":
            cash += gross - fees
    return cash


def _log_missed(portfolio_id: int, scheduled: date, reason: str, details: dict) -> None:
    try:
        _supabase().table("paper_missed_rebalances").insert({
            "portfolio_id": portfolio_id, "scheduled_date": scheduled.isoformat(),
            "reason": reason, "details": details,
        }).execute()
    except Exception as e:
        logger.error(f"failed to log missed rebalance: {e}")


def run_weekly_rebalance() -> None:
    """Select top 10, sell out-of-top, buy new equally-weighted from cash freed + last cash."""
    portfolio_id = bootstrap_portfolio()
    today_iso = date.today().isoformat()
    logger.info(f"=== REBALANCE {PORTFOLIO_NAME} {today_iso} ===")

    target = _load_top_n_scores(TARGET_COUNT)
    if not target:
        logger.error("ticker_scores empty — aborting")
        _log_missed(portfolio_id, date.today(), "SCORING_INCOMPLETE", {"reason": "ticker_scores empty"})
        return
    target_set = {t["ticker"] for t in target}

    current = _load_open_positions(portfolio_id)
    last_nav, _ = _last_nav(portfolio_id)
    cash_available = _compute_cash(portfolio_id)
    sb = _supabase()
    trades = 0

    # SELL: positions hors top 10
    for ticker, pos in current.items():
        if ticker in target_set:
            continue
        price = _fetch_quote(ticker)
        if price is None:
            logger.warning(f"SELL skipped {ticker}: quote unavailable")
            continue
        shares = float(pos["shares"])
        gross = shares * price
        fees = gross * FEES_BPS / 10000
        sb.table("paper_rebalances").insert({
            "portfolio_id": portfolio_id, "rebalance_date": today_iso,
            "action": "SELL", "ticker": ticker, "shares": shares, "price": price,
            "fees": fees, "slippage": 0,
            "score_at_decision": None, "rationale": "Out of top 10",
            "prev_hash": None,
            "row_hash": _placeholder_row_hash(portfolio_id, today_iso, ticker, "SELL", shares),
        }).execute()
        sb.table("paper_positions").delete().eq("portfolio_id", portfolio_id).eq("ticker", ticker).execute()
        cash_available += gross - fees
        trades += 1
        logger.info(f"SELL  {ticker:6s} {shares:8.4f} @ {price:8.2f} = ${gross-fees:.2f} (fees ${fees:.2f})")

    # BUY: nouvelles entrées (target \ current)
    new_entries = [t for t in target if t["ticker"] not in current]
    per_position = last_nav / TARGET_COUNT  # 10% NAV par ligne
    for entry in new_entries:
        ticker = entry["ticker"]
        price = _fetch_quote(ticker)
        if price is None:
            logger.warning(f"BUY skipped {ticker}: quote unavailable")
            continue
        budget = min(per_position, cash_available)
        if budget <= 0:
            logger.warning(f"BUY {ticker} skipped: no cash left ({cash_available:.2f})")
            continue
        # Solve: shares*price + shares*price*fees_bps/10000 = budget
        cost_factor = price * (1 + FEES_BPS / 10000)
        shares = budget / cost_factor
        gross = shares * price
        fees = gross * FEES_BPS / 10000
        cost = gross + fees
        sb.table("paper_rebalances").insert({
            "portfolio_id": portfolio_id, "rebalance_date": today_iso,
            "action": "BUY", "ticker": ticker, "shares": shares, "price": price,
            "fees": fees, "slippage": 0,
            "score_at_decision": entry["score"],
            "rationale": f"Top 10 entry (score {entry['score']})",
            "prev_hash": None,
            "row_hash": _placeholder_row_hash(portfolio_id, today_iso, ticker, "BUY", shares),
        }).execute()
        sb.table("paper_positions").upsert({
            "portfolio_id": portfolio_id, "ticker": ticker, "side": "LONG",
            "shares": shares, "entry_price": price, "entry_date": today_iso,
        }, on_conflict="portfolio_id,ticker").execute()
        cash_available -= cost
        trades += 1
        logger.info(f"BUY   {ticker:6s} {shares:8.4f} @ {price:8.2f} = ${cost:.2f} (fees ${fees:.2f}, score {entry['score']})")

    # Persist cash + NAV right at rebalance close so run_daily_nav has
    # a correct `last_cash` to start from (otherwise we double-count cash
    # + positions when computing NAV later in the day).
    # Idempotent: skip if a row already exists for today (append-only constraint).
    #
    # IMPORTANT (2026-05-18) : on n'ecrit cette NAV row QUE si on a effectivement
    # trade aujourd'hui. Si trades == 0 (top 10 stable), le `long_at_entry` ci-dessous
    # reflete les achats des semaines passees (PAS le prix du jour), donc on ecrirait
    # une NAV figee et on bloquerait run_daily_nav du soir par idempotency. Sans
    # trade, on laisse run_daily_nav (22h UTC) faire son mark-to-market normalement.
    has_today_nav = (sb.table("paper_nav_history").select("id")
                       .eq("portfolio_id", portfolio_id).eq("date", today_iso).limit(1).execute()).data
    if trades > 0 and not has_today_nav:
        # NAV at rebalance close = positions valued at their just-paid entry price
        # + cash residual. Equals the pre-rebalance NAV minus fees.
        post_positions = _load_open_positions(portfolio_id)
        long_at_entry = sum(float(p["shares"]) * float(p["entry_price"]) for p in post_positions.values())
        new_nav = long_at_entry + cash_available
        sb.table("paper_nav_history").insert({
            "portfolio_id": portfolio_id, "date": today_iso,
            "nav": round(new_nav, 2), "cash_balance": round(cash_available, 2),
            "cash_interest": 0, "borrow_cost": 0,
            "daily_return": round((new_nav / last_nav - 1) if last_nav > 0 else 0.0, 6),
            "cumulative_return": round(new_nav / INITIAL_CAPITAL - 1, 6),
            "drawdown": None,
        }).execute()
        logger.info(f"NAV row written at rebalance close: ${new_nav:.2f} (long ${long_at_entry:.2f} + cash ${cash_available:.2f})")

    logger.info(f"=== REBALANCE done: {trades} trade(s), cash now ~${cash_available:.2f} ===")


def run_daily_nav() -> None:
    """Mark-to-market positions, append paper_nav_history (idempotent per day)."""
    portfolio_id = bootstrap_portfolio()
    today_iso = date.today().isoformat()
    sb = _supabase()

    if (sb.table("paper_nav_history").select("id")
          .eq("portfolio_id", portfolio_id).eq("date", today_iso).limit(1).execute()).data:
        logger.info(f"NAV {today_iso} already recorded — skip (append-only)")
        return

    positions = _load_open_positions(portfolio_id)
    long_value = 0.0
    for ticker, pos in positions.items():
        price = _fetch_quote(ticker) or float(pos["entry_price"])
        long_value += float(pos["shares"]) * price

    last_nav, _ = _last_nav(portfolio_id)
    cash = _compute_cash(portfolio_id)
    nav = long_value + cash
    daily_return = (nav / last_nav - 1) if last_nav > 0 else 0.0

    sb.table("paper_nav_history").insert({
        "portfolio_id": portfolio_id, "date": today_iso,
        "nav": round(nav, 2), "cash_balance": round(cash, 2),
        "cash_interest": 0, "borrow_cost": 0,
        "daily_return": round(daily_return, 6),
        "cumulative_return": round(nav / INITIAL_CAPITAL - 1, 6),
        "drawdown": None,
    }).execute()
    logger.info(f"NAV {today_iso}: ${nav:.2f} (long ${long_value:.2f} + cash ${cash:.2f}), daily {daily_return:+.4%}")


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--bootstrap", action="store_true")
    p.add_argument("--rebalance", action="store_true")
    p.add_argument("--nav", action="store_true")
    a = p.parse_args()
    if a.bootstrap: bootstrap_portfolio()
    if a.rebalance: run_weekly_rebalance()
    if a.nav: run_daily_nav()
    if not (a.bootstrap or a.rebalance or a.nav): p.print_help()
