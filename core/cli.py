"""
AlphaBrief CLI — usage local
=============================
  python -m core.cli analyze AAPL MSFT NVDA
  python -m core.cli run-all
  python -m core.cli status
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path


# ── .env loader ───────────────────────────────────────────────────────────────

def _load_dotenv() -> None:
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val

_load_dotenv()

from core.generator import generate_card  # noqa: E402


# ── Supabase REST + sélection des tickers ─────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

STALE_AFTER_H = 20
DELAY_S = 2

DEFAULT_TICKERS: list[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
    "JPM", "V", "UNH", "COST", "ADBE", "CRM", "COIN", "DPZ",
]


def _sb_get(path: str) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    req = urllib.request.Request(url, headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except (urllib.error.HTTPError, urllib.error.URLError, OSError):
        return []


def fetch_tickers_to_score() -> list[str]:
    tickers: set[str] = set(DEFAULT_TICKERS)

    for r in _sb_get("watchlist_tickers?select=ticker"):
        if r.get("ticker"):
            tickers.add(r["ticker"].upper())

    now = datetime.now(timezone.utc)
    skip: set[str] = set()
    for r in _sb_get("ticker_scores?select=ticker,computed_at"):
        ticker = (r.get("ticker") or "").upper()
        if not ticker:
            continue
        tickers.add(ticker)
        computed_at = r.get("computed_at")
        if computed_at:
            try:
                dt = datetime.fromisoformat(computed_at.replace("Z", "+00:00"))
                if (now - dt) < timedelta(hours=STALE_AFTER_H):
                    skip.add(ticker)
            except Exception:
                pass

    return sorted(tickers - skip)


def _print_header(title: str) -> None:
    print(f"\n{'-' * 50}")
    print(f"  {title}")
    print(f"{'-' * 50}")


def _analyze_tickers(tickers: list[str]) -> None:
    total = len(tickers)
    success, failed = [], []

    for i, ticker in enumerate(tickers, 1):
        print(f"[{i}/{total}] {ticker} ...", end=" ", flush=True)
        try:
            card = generate_card(ticker)
            score = card.get("scores", {}).get("potential_score", "?")
            label = card.get("scores", {}).get("score_label", "")
            print(f"OK  {score}/100 ({label})")
            success.append(ticker)
        except KeyboardInterrupt:
            print("\nInterrompu.")
            break
        except Exception as e:
            print(f"FAIL  {e}")
            failed.append(ticker)

        if i < total:
            time.sleep(DELAY_S)

    print(f"\nSuccès={len(success)}  Échecs={len(failed)}")
    if failed:
        print(f"Échecs : {', '.join(failed)}")


# ── Commandes ─────────────────────────────────────────────────────────────────

def cmd_analyze(tickers: list[str]) -> None:
    if not tickers:
        print("Usage : python -m core.cli analyze AAPL MSFT ...")
        sys.exit(1)
    tickers = [t.upper() for t in tickers]
    _print_header(f"Analyse de {len(tickers)} ticker(s) : {', '.join(tickers)}")
    _analyze_tickers(tickers)


def cmd_run_all() -> None:
    _print_header("Run-all — identique au scheduler VPS")
    tickers = fetch_tickers_to_score()
    if not tickers:
        print("Tous les tickers sont frais. Rien à faire.")
        return
    print(f"{len(tickers)} ticker(s) à scorer.\n")
    _analyze_tickers(tickers)


def cmd_status() -> None:
    _print_header("Statut des tickers (Supabase)")

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠  SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY manquants dans .env")
        sys.exit(1)

    rows = _sb_get("ticker_scores?select=ticker,company_name,score_total,computed_at&order=computed_at.desc")

    if not rows:
        print("Aucune donnée en base.")
        return

    now = datetime.now(timezone.utc)
    stale_limit = timedelta(hours=STALE_AFTER_H)

    fresh, stale = [], []
    for r in rows:
        ticker = r.get("ticker", "?")
        name = (r.get("company_name") or "")[:28]
        score = r.get("score_total", "?")
        computed_at = r.get("computed_at") or ""
        age_str = "jamais"
        is_stale = True
        if computed_at:
            try:
                dt = datetime.fromisoformat(computed_at.replace("Z", "+00:00"))
                age = now - dt
                hours = int(age.total_seconds() / 3600)
                age_str = f"{hours}h" if hours < 48 else f"{age.days}j"
                is_stale = age > stale_limit
            except Exception:
                pass
        entry = (ticker, name, score, age_str)
        (stale if is_stale else fresh).append(entry)

    def _print_rows(entries: list, label: str, icon: str) -> None:
        if not entries:
            return
        print(f"\n{icon}  {label} ({len(entries)})")
        print(f"  {'TICKER':<8} {'NOM':<30} {'SCORE':>5}  ÂGE")
        for ticker, name, score, age in entries:
            score_str = f"{score:>3}/100" if isinstance(score, int) else f"  {'?':>3}"
            print(f"  {ticker:<8} {name:<30} {score_str}  {age}")

    _print_rows(fresh, f"Frais (< {STALE_AFTER_H}h)", "OK")
    _print_rows(stale, f"A rescorer (> {STALE_AFTER_H}h)", "!!")
    print()


# ── Entrypoint ────────────────────────────────────────────────────────────────

def main() -> None:
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd = args[0].lower()
    rest = args[1:]

    if cmd == "analyze":
        cmd_analyze(rest)
    elif cmd == "run-all":
        cmd_run_all()
    elif cmd == "status":
        cmd_status()
    else:
        print(f"Commande inconnue : {cmd}")
        print("Commandes : analyze, run-all, status")
        sys.exit(1)


if __name__ == "__main__":
    main()
