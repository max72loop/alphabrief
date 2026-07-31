#!/usr/bin/env python3
"""Backtest AlphaBrief — rejoue les snapshots de scores_history vs perf yfinance.

Pour chaque (ticker, date, score) du SQLite, on regarde la perf prix à J+5,
J+30, J+90. On agrège par tranche de score pour répondre à la question :
"un score de 70 prédit-il vraiment une hausse sur 30 jours ?".

Sortie : /root/alphabrief/data/backtests/backtest_latest.json + backtest_YYYYMMDD.json.

Usage:
    python scripts/backtest.py
    python scripts/backtest.py --limit-tickers 5    # mode debug
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yfinance as yf

DB_PATH = Path("/root/alphabrief/data/mytrader.db")
OUT_DIR = Path("/root/alphabrief/data/backtests")
OUT_DIR.mkdir(parents=True, exist_ok=True)

SCORE_BUCKETS = [
    ("<40", 0, 40),
    ("40-50", 40, 50),
    ("50-60", 50, 60),
    ("60-70", 60, 70),
    ("70+", 70, 101),
]
WINDOWS = [5, 30, 90]


def fetch_closes(ticker: str, start: str, end: str) -> dict[str, float]:
    """Daily close, ajusté splits/divs. Retourne {date_iso: close}."""
    try:
        df = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True, threads=False)
        if df.empty:
            return {}
        # auto_adjust=True peut produire des colonnes simples ou multi-index
        if hasattr(df.columns, "levels"):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return {d.strftime("%Y-%m-%d"): float(c) for d, c in df["Close"].items() if c == c}
    except Exception as e:
        print(f"  ! yfinance fail for {ticker}: {e}", file=sys.stderr)
        return {}


def closest_close(closes: dict[str, float], target: datetime.date, fwd_days: int) -> float | None:
    """Cherche le close du jour ouvré le plus proche après (target + fwd_days)."""
    end = target + timedelta(days=fwd_days)
    for offset in range(8):  # walk forward up to 8 days to skip weekends/holidays
        iso = (end + timedelta(days=offset)).strftime("%Y-%m-%d")
        if iso in closes:
            return closes[iso]
    return None


def closest_close_at_or_after(closes: dict[str, float], target_iso: str) -> float | None:
    """Close du jour `target_iso` ou suivant ouvré."""
    base = datetime.strptime(target_iso, "%Y-%m-%d").date()
    for offset in range(5):
        iso = (base + timedelta(days=offset)).strftime("%Y-%m-%d")
        if iso in closes:
            return closes[iso]
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit-tickers", type=int, default=0, help="Debug: limit to N first tickers")
    args = p.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT ticker, score, date(date) AS d FROM scores_history ORDER BY ticker, d"
    ).fetchall()

    by_ticker: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for r in rows:
        by_ticker[r["ticker"]].append((r["d"], r["score"]))

    tickers = sorted(by_ticker.keys())
    if args.limit_tickers:
        tickers = tickers[: args.limit_tickers]

    all_dates = [d for snaps in by_ticker.values() for d, _ in snaps]
    fetch_start = min(all_dates)
    fetch_end = (
        datetime.strptime(max(all_dates), "%Y-%m-%d") + timedelta(days=max(WINDOWS) + 20)
    ).strftime("%Y-%m-%d")

    print(f"Backtest {len(tickers)} tickers, {sum(len(s) for s in by_ticker.values())} snapshots "
          f"(range {fetch_start} → {fetch_end})")

    # Bucket -> window -> stats accumulators
    agg = {b[0]: {w: {"perfs": [], "wins": 0} for w in WINDOWS} for b in SCORE_BUCKETS}
    snapshots_used = 0

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i:>2}/{len(tickers)}] {ticker:<8}", end=" ", flush=True)
        closes = fetch_closes(ticker, fetch_start, fetch_end)
        if not closes:
            print("(no data)")
            continue

        n_used = 0
        for date_iso, score in by_ticker[ticker]:
            base_close = closest_close_at_or_after(closes, date_iso)
            if base_close is None:
                continue
            bucket = next((b[0] for b in SCORE_BUCKETS if b[1] <= score < b[2]), None)
            if bucket is None:
                continue
            base_date = datetime.strptime(date_iso, "%Y-%m-%d").date()
            for w in WINDOWS:
                fwd = closest_close(closes, base_date, w)
                if fwd is None:
                    continue
                perf = (fwd - base_close) / base_close * 100
                agg[bucket][w]["perfs"].append(perf)
                if perf > 0:
                    agg[bucket][w]["wins"] += 1
            n_used += 1
        snapshots_used += n_used
        print(f"{n_used} snaps")

    # Compose payload
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "tickers": len(tickers),
        "snapshots_used": snapshots_used,
        "windows_days": WINDOWS,
        "buckets": [],
    }
    for bname, lo, hi in SCORE_BUCKETS:
        bucket_row = {"bucket": bname, "score_range": [lo, hi]}
        for w in WINDOWS:
            perfs = agg[bname][w]["perfs"]
            n = len(perfs)
            if n == 0:
                bucket_row[f"d{w}"] = {"n": 0, "avg_perf_pct": None, "hit_rate_pct": None}
                continue
            avg = sum(perfs) / n
            hr = agg[bname][w]["wins"] / n * 100
            bucket_row[f"d{w}"] = {
                "n": n,
                "avg_perf_pct": round(avg, 2),
                "hit_rate_pct": round(hr, 1),
            }
        out["buckets"].append(bucket_row)

    latest_path = OUT_DIR / "backtest_latest.json"
    dated_path = OUT_DIR / f"backtest_{datetime.utcnow().strftime('%Y%m%d')}.json"
    latest_path.write_text(json.dumps(out, indent=2))
    dated_path.write_text(json.dumps(out, indent=2))
    print(f"\nWritten {latest_path}")

    # Console summary table
    print("\n=== Hit rate par tranche de score ===")
    print(f"{'Bucket':<8} | {'J+5 n/perf/hit':<22} | {'J+30 n/perf/hit':<22} | {'J+90 n/perf/hit':<22}")
    print("-" * 88)
    for row in out["buckets"]:
        cells = [f"{row['bucket']:<8}"]
        for w in WINDOWS:
            d = row[f"d{w}"]
            if d["n"] == 0:
                cells.append(f"{'—':<22}")
            else:
                cells.append(f"n={d['n']:<4} {d['avg_perf_pct']:>+6.2f}%  hit={d['hit_rate_pct']:>4.1f}%")
        print(" | ".join(cells))


if __name__ == "__main__":
    main()
