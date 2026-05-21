#!/usr/bin/env python3
"""
Reproduit l'audit scoring AlphaBrief — table décomposée des scores du jour.

Lit:
  - /root/alphabrief/data/mytrader.db (scores_history, card_cache)
  - /root/alphabrief/data/cache/*_fundamentals.json (TTL 24h)

Sortie:
  - Table par ticker : score affiché, sous-scores, confidence, factor reverse,
    score brut reconstruit, état du cache fundamentals (valid/poison/partial).

Usage:
  python3 /root/alphabrief/audits/reproduce_scoring_audit.py [--date YYYY-MM-DD]
"""
import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DB_PATH = Path("/root/alphabrief/data/mytrader.db")
CACHE_DIR = Path("/root/alphabrief/data/cache")


def cache_status(ticker: str) -> tuple[str, int, int, str]:
    p = CACHE_DIR / f"{ticker.upper()}_fundamentals.json"
    if not p.exists():
        return ("absent", 0, 0, "")
    try:
        c = json.loads(p.read_text())
        fin = c["data"].get("financials", {})
        val = c["data"].get("valuation", {})
        all_fields = {**fin, **val}
        n_total = len(all_fields)
        n_valid = sum(1 for v in all_fields.values() if v is not None)
        fetched = c.get("fetched_at", "?")[:19]
        if n_valid == 0:
            return ("POISON", n_valid, n_total, fetched)
        if n_valid < 5:
            return ("partial", n_valid, n_total, fetched)
        return ("ok", n_valid, n_total, fetched)
    except Exception as e:
        return (f"err:{e}", 0, 0, "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYY-MM-DD (default = today UTC)")
    args = ap.parse_args()
    target_date = args.date or datetime.utcnow().strftime("%Y-%m-%d")

    if not DB_PATH.exists():
        sys.exit(f"DB not found: {DB_PATH}")

    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row

    rows = con.execute("""
        SELECT s.ticker, s.score, s.confidence, s.date, c.card_json
        FROM scores_history s
        INNER JOIN (
            SELECT ticker, MAX(date) d FROM scores_history GROUP BY ticker
        ) m ON s.ticker = m.ticker AND s.date = m.d
        LEFT JOIN card_cache c ON s.ticker = c.ticker
        WHERE s.date LIKE ?
        ORDER BY s.score DESC
    """, (f"{target_date}%",)).fetchall()

    print(f"# AlphaBrief scoring audit — {target_date}")
    print(f"# {len(rows)} tickers scored")
    print()
    print(f"{'TICKER':<10} {'TOT':>3} {'FUN':>3} {'TEC':>3} {'MOM':>3} {'CONF':>4} "
          f"{'FACT':>5} {'RAW':>5} {'F_RAW':>5} | {'CACHE':<10} {'VALID':>3}/{'TOT':<3} {'FETCHED':<19}")
    print("-" * 115)

    poisoned = []
    for r in rows:
        c = json.loads(r["card_json"]) if r["card_json"] else {}
        sc = c.get("scores", {}) if c else {}
        conf = r["confidence"] or 0
        factor = 0.5 + 0.5 * conf / 100
        fun = sc.get("fundamentals_score") or 0
        tec = sc.get("technicals_score") or 0
        mom = sc.get("momentum_score") or 0
        raw_tot = (r["score"] / factor) if factor > 0 else 0
        raw_fun = (fun / factor) if factor > 0 else 0
        status, nv, nt, ft = cache_status(r["ticker"])
        if status == "POISON":
            poisoned.append(r["ticker"])
        print(f"{r['ticker']:<10} {r['score']:>3} {fun:>3} {tec:>3} {mom:>3} "
              f"{conf:>4} {factor:>5.3f} {raw_tot:>5.1f} {raw_fun:>5.1f} | "
              f"{status:<10} {nv:>3}/{nt:<3} {ft:<19}")

    print()
    print(f"Caches poisoned (0/29 valid fundamentals): {len(poisoned)} / {len(rows)}")
    if poisoned:
        print("  " + ", ".join(poisoned))


if __name__ == "__main__":
    main()
