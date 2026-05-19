"""
AlphaBrief Scheduler
====================
Lancé chaque nuit par PM2 (cron 2h00). Récupère tous les tickers suivis
dans Supabase + une liste de base, filtre ceux déjà frais (< 20h), et
recalcule les autres en séquence avec un délai anti-rate-limit.

Usage manuel : python -m core.scheduler_runner
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ── .env loader (sans dépendance externe) ────────────────────────────────────

def _load_dotenv() -> None:
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val

_load_dotenv()

# ── Imports projet (après dotenv) ─────────────────────────────────────────────

from core.generator import generate_card          # noqa: E402
from core.alert_engine import process_alerts      # noqa: E402
from core.providers.events_yf import sync_events_for  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
RESEND_KEY   = os.environ.get("RESEND_API_KEY", "") or None

# Délai entre deux tickers (secondes) — évite les rate limits Yahoo/FMP
DELAY_S = 3

# Ne pas rescorer si calculé il y a moins de N heures
STALE_AFTER_H = 20

# Tickers toujours présents, même si aucun watchlist
DEFAULT_TICKERS: list[str] = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
    "JPM", "V", "UNH", "COST", "ADBE", "CRM", "COIN", "DPZ",
]


# ── Supabase REST helpers ─────────────────────────────────────────────────────

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
    except urllib.error.HTTPError as e:
        logger.warning(f"Supabase GET {path} → HTTP {e.code}: {e.read()[:200]}")
        return []
    except Exception as e:
        logger.warning(f"Supabase GET {path} failed: {e}")
        return []


# ── Snapshot des scores actuels (avant run) ───────────────────────────────────

def fetch_current_scores() -> dict[str, dict[str, Any]]:
    """
    Récupère score_total et rsi_14 pour tous les tickers déjà en base.
    Retourne un dict {ticker: {"score": int, "rsi": float|None}}.
    """
    rows = _sb_get(
        "ticker_scores?select=ticker,score_total,market_data"
    )
    result: dict[str, dict[str, Any]] = {}
    for r in rows:
        ticker = (r.get("ticker") or "").upper()
        if not ticker:
            continue
        market_data = r.get("market_data") or {}
        result[ticker] = {
            "score": r.get("score_total"),
            "rsi":   market_data.get("rsi_14"),
        }
    return result


# ── Sélection des tickers à scorer ───────────────────────────────────────────

def fetch_tickers_to_score() -> list[str]:
    """
    Retourne la liste triée des tickers à scorer aujourd'hui :
    - Union de : DEFAULT_TICKERS + watchlist_tickers + ticker_scores existants
    - Filtre : retire ceux dont computed_at < STALE_AFTER_H heures
    """
    tickers: set[str] = set(DEFAULT_TICKERS)

    # Watchlists utilisateurs
    wl_rows = _sb_get("watchlist_tickers?select=ticker")
    for r in wl_rows:
        if r.get("ticker"):
            tickers.add(r["ticker"].upper())

    # Tickers déjà connus + fraîcheur
    now = datetime.now(timezone.utc)
    skip: set[str] = set()
    score_rows = _sb_get("ticker_scores?select=ticker,computed_at")
    for r in score_rows:
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

    to_score = sorted(tickers - skip)
    logger.info(
        f"Tickers total={len(tickers)} | frais (skip)={len(skip)} | "
        f"à scorer={len(to_score)}"
    )
    return to_score


# ── Runner principal ──────────────────────────────────────────────────────────

def run() -> None:
    start = datetime.now()
    logger.info("=" * 60)
    logger.info(f"AlphaBrief Scheduler démarré — {start.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)

    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY manquants — arrêt.")
        sys.exit(1)

    # Snapshot des scores avant le run (pour comparaison dans l'alert engine)
    prev_scores = fetch_current_scores()
    logger.info(f"Snapshot pré-run : {len(prev_scores)} ticker(s) en base.")

    tickers = fetch_tickers_to_score()
    total = len(tickers)

    if total == 0:
        logger.info("Tous les tickers sont frais. Rien à faire.")
        return

    success: list[str] = []
    failed: list[str] = []

    for i, ticker in enumerate(tickers, 1):
        logger.info(f"[{i}/{total}] {ticker} ...")
        try:
            card = generate_card(ticker)
            score = card.get("scores", {}).get("potential_score", "?")
            label = card.get("scores", {}).get("score_label", "")
            logger.info(f"  ✓ {ticker} → {score}/100 ({label})")
            success.append(ticker)

            # Détection d'alertes — comparaison avec le snapshot pré-run
            prev = prev_scores.get(ticker.upper(), {})
            process_alerts(
                ticker=ticker,
                card=card,
                old_score=prev.get("score"),
                old_rsi=prev.get("rsi"),
                sb_url=SUPABASE_URL,
                sb_key=SUPABASE_KEY,
                resend_key=RESEND_KEY,
            )

            # Sync earnings/dividend events (best-effort, n'échoue pas le ticker)
            try:
                sync_events_for(ticker)
            except Exception as e:
                logger.debug(f"  events sync skipped for {ticker}: {e}")
        except KeyboardInterrupt:
            logger.warning("Interruption utilisateur — arrêt propre.")
            break
        except Exception as e:
            logger.error(f"  ✗ {ticker} échoué : {e}")
            failed.append(ticker)

        if i < total:
            time.sleep(DELAY_S)

    elapsed = datetime.now() - start
    logger.info("=" * 60)
    logger.info(
        f"Terminé en {elapsed}. "
        f"Succès={len(success)} | Échecs={len(failed)}"
    )
    if failed:
        logger.warning(f"Tickers en échec : {', '.join(failed)}")
    logger.info("=" * 60)


if __name__ == "__main__":
    run()
