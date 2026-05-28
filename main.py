"""
AlphaBrief Agent — Scoring autonome + monitoring quotidien.

Couches :
  1. Scoring watchlist + rapport quotidien : cron 7h (un seul message Telegram fusionne)
  2. Health check : toutes les 30 min (Flask alive, yfinance OK)
  3. Cache cleanup : 3h du matin (purge fichiers expirés)

Usage :
  pm2 start /root/agents/alphabrief/main.py --interpreter python3
  python3 /root/agents/alphabrief/main.py --score        # scoring immédiat
  python3 /root/agents/alphabrief/main.py --report       # rapport immédiat
  python3 /root/agents/alphabrief/main.py --health       # health check
  python3 /root/agents/alphabrief/main.py --stats        # stats rapides
"""

import sys
sys.path.insert(0, "/root")
sys.path.insert(0, "/root/alphabrief")

import json
import time
import sqlite3
import argparse
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from apscheduler.schedulers.blocking import BlockingScheduler

from alfred.shared.config import cfg
from alfred.shared.logger import get_logger
from alfred.shared.telegram import notify, Priority
from alfred.shared.redis_client import redis_client, publish_event

logger = get_logger("alphabrief")

# ── Paths ─────────────────────────────────────────────────────────────────
AGENT_DIR    = Path("/root/agents/alphabrief")
AB_DIR       = Path("/root/alphabrief")
DB_PATH      = AB_DIR / "data" / "mytrader.db"
CACHE_DIR    = AB_DIR / "data" / "cache"
REPORTS_DIR  = AGENT_DIR / "data" / "daily_reports"
SNAPSHOTS_DIR = AGENT_DIR / "snapshots"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)
SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)

# ── Config ────────────────────────────────────────────────────────────────
CONFIG_PATH = AGENT_DIR / "config.json"

DEFAULT_CONFIG = {
    "thresholds": {
        "alert_score_delta": 15,
        "strong_buy_score": 75,
        "cache_max_age_hours": 48,
    },
    "crons": {
        "scoring_hour": 7,
        "report_hour": 9,
        "health_check_min": 30,
        "cache_cleanup_hour": 3,
    },
}


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except Exception:
            pass
    CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
    return DEFAULT_CONFIG


acfg = _load_config()
THRESH = acfg["thresholds"]
CRONS = acfg["crons"]

# ── SQLite helpers (standalone, no Flask context) ─────────────────────────

def _db_conn():
    con = sqlite3.connect(str(DB_PATH))
    con.row_factory = sqlite3.Row
    return con


def _get_watchlist() -> list[str]:
    with _db_conn() as con:
        rows = con.execute("SELECT ticker FROM watchlist").fetchall()
    return [r["ticker"] for r in rows]


def _get_latest_score(ticker: str) -> int | None:
    with _db_conn() as con:
        row = con.execute(
            "SELECT score FROM scores_history WHERE ticker = ? ORDER BY date DESC LIMIT 1",
            (ticker.upper(),),
        ).fetchone()
    return row["score"] if row else None


def _save_score(ticker: str, score: int, confidence: int):
    now = datetime.now(timezone.utc).isoformat()
    with _db_conn() as con:
        con.execute(
            "INSERT INTO scores_history(ticker, score, confidence, date) VALUES (?,?,?,?)",
            (ticker.upper(), score, confidence, now),
        )
        con.commit()


def _save_card(ticker: str, card: dict):
    now = datetime.now(timezone.utc).isoformat()
    with _db_conn() as con:
        con.execute(
            "INSERT OR REPLACE INTO card_cache(ticker, generated_at, card_json) VALUES (?,?,?)",
            (ticker.upper(), now, json.dumps(card, ensure_ascii=False)),
        )
        con.commit()


def _save_alert(ticker: str, alert_type: str, score_old: int | None, score_new: int, message: str):
    now = datetime.now(timezone.utc).isoformat()
    with _db_conn() as con:
        if alert_type == "STRONG_BUY":
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            existing = con.execute(
                "SELECT 1 FROM alerts WHERE ticker=? AND alert_type='STRONG_BUY' AND created_at>?",
                (ticker.upper(), cutoff),
            ).fetchone()
            if existing:
                return
        con.execute(
            "INSERT INTO alerts(ticker, alert_type, score_old, score_new, message, read, created_at) VALUES (?,?,?,?,?,0,?)",
            (ticker.upper(), alert_type, score_old, score_new, message, now),
        )
        con.commit()


def _get_unread_alerts() -> list[dict]:
    with _db_conn() as con:
        rows = con.execute(
            "SELECT ticker, alert_type, score_old, score_new, message, created_at FROM alerts WHERE read=0 ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def _get_all_scores() -> list[dict]:
    """Dernier score de chaque ticker (all-time, conserve pour debug ou usages externes)."""
    with _db_conn() as con:
        rows = con.execute("""
            SELECT s.ticker, s.score, s.confidence, s.date
            FROM scores_history s
            INNER JOIN (
                SELECT ticker, MAX(date) as max_date
                FROM scores_history GROUP BY ticker
            ) latest ON s.ticker = latest.ticker AND s.date = latest.max_date
            ORDER BY s.score DESC
        """).fetchall()
    return [dict(r) for r in rows]


def _get_today_scores(today_prefix: str | None = None) -> list[dict]:
    """Scores du jour uniquement (dernier score de chaque ticker score aujourd'hui)."""
    if today_prefix is None:
        today_prefix = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    pattern = f"{today_prefix}%"
    with _db_conn() as con:
        rows = con.execute("""
            SELECT s.ticker, s.score, s.confidence, s.date
            FROM scores_history s
            INNER JOIN (
                SELECT ticker, MAX(date) as max_date
                FROM scores_history
                WHERE date LIKE ?
                GROUP BY ticker
            ) latest ON s.ticker = latest.ticker AND s.date = latest.max_date
            ORDER BY s.score DESC
        """, (pattern,)).fetchall()
    return [dict(r) for r in rows]


# ── Couche 1 — Scoring watchlist ──────────────────────────────────────────

def scoring_run():
    """Score tous les tickers de la watchlist. Génère des alertes si mouvement."""
    logger.info("=== SCORING WATCHLIST ===")

    tickers = _get_watchlist()
    if not tickers:
        logger.info("Watchlist vide, rien à scorer")
        return

    # Import du scoring pipeline AlphaBrief
    from core.generator import generate_card
    from core.providers import fmp_client
    # Dual-write Supabase : import isolé, l'absence de credentials ne bloque pas
    # le scoring SQLite — write_score renvoie False si Config.SUPABASE_URL/KEY vide.
    try:
        from app.storage.supabase_writer import write_score as sb_write_score
    except Exception as e:
        logger.error(f"supabase_writer import failed — Supabase dual-write disabled: {e}")
        sb_write_score = None

    try:
        from core.providers.events_yf import sync_events_for as sb_sync_events
    except Exception as e:
        logger.error(f"events_yf import failed — ticker_events sync disabled: {e}")
        sb_sync_events = None

    logger.info(f"{len(tickers)} tickers à scorer")
    publish_event("alphabrief:scoring_started", {"count": len(tickers)})

    scored = 0
    sb_ok = 0
    sb_failed = 0
    alerts_generated = []

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = {executor.submit(generate_card, t): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            t0 = time.monotonic()
            log_row = {
                "evt": "ticker_scored",
                "ticker": ticker,
                "status": "unknown",
                "score": None,
                "confidence": None,
                "duration_ms": None,
                "error": None,
                "supabase": "skipped",
            }
            try:
                card = future.result()
                score = card.get("scores", {}).get("potential_score")
                confidence = card.get("scores", {}).get("confidence_score", 0)
                log_row["score"] = score
                log_row["confidence"] = confidence

                if score is None:
                    log_row["status"] = "skipped_no_score"
                    logger.warning(json.dumps(log_row))
                    continue

                prev_score = _get_latest_score(ticker)
                _save_card(ticker, card)
                _save_score(ticker, score, confidence)
                scored += 1
                log_row["status"] = "ok"

                # Alertes
                alert = _check_alert(ticker, score, prev_score)
                if alert:
                    alerts_generated.append(alert)

                # Dual-write Supabase — isolé par ticker
                if sb_write_score is not None:
                    try:
                        ok = sb_write_score(ticker, card)
                        if ok:
                            sb_ok += 1
                            log_row["supabase"] = "ok"
                        else:
                            sb_failed += 1
                            log_row["supabase"] = "failed"
                    except Exception as sb_err:
                        sb_failed += 1
                        log_row["supabase"] = f"error: {sb_err}"
                        logger.error(f"Supabase write {ticker}: {sb_err}")

                # Sync ticker_events (earnings + dividend) — isolé, échec silencieux
                if sb_sync_events is not None:
                    try:
                        n_ev = sb_sync_events(ticker)
                        log_row["events"] = n_ev
                    except Exception as ev_err:
                        log_row["events"] = f"error: {ev_err}"
                        logger.warning(f"ticker_events sync {ticker}: {ev_err}")

            except Exception as e:
                log_row["status"] = "error"
                log_row["error"] = str(e)
            finally:
                log_row["duration_ms"] = int((time.monotonic() - t0) * 1000)
                logger.info(json.dumps(log_row))

    fmp_calls = fmp_client.get_call_count()
    fmp_client.clear_cache()   # le daemon vit en continu, on évite la croissance silencieuse du _cache process-wide

    summary = f"📊 Scoring terminé : {scored}/{len(tickers)} tickers"
    if sb_write_score is not None:
        summary += f" | Supabase: {sb_ok} OK / {sb_failed} KO"
    summary += f" | FMP calls: {fmp_calls}"
    if alerts_generated:
        summary += f"\n🔔 {len(alerts_generated)} alerte(s) :"
        for a in alerts_generated:
            summary += f"\n  {a}"

    logger.info(summary)
    publish_event("alphabrief:scoring_done", {
        "scored": scored, "total": len(tickers),
        "supabase_ok": sb_ok, "supabase_failed": sb_failed,
        "alerts": len(alerts_generated),
        "fmp_calls": fmp_calls,
    })
    return {
        "scored": scored,
        "total": len(tickers),
        "sb_ok": sb_ok,
        "sb_failed": sb_failed,
        "sb_enabled": sb_write_score is not None,
        "alerts_generated": alerts_generated,
    }


def _check_alert(ticker: str, score: int, prev_score: int | None) -> str | None:
    delta_threshold = THRESH["alert_score_delta"]
    strong_buy = THRESH["strong_buy_score"]

    if score >= strong_buy:
        msg = f"{ticker} — Score exceptionnel : {score}/100"
        _save_alert(ticker, "STRONG_BUY", prev_score, score, msg)
        return msg

    if prev_score is not None:
        delta = score - prev_score
        if delta >= delta_threshold:
            msg = f"{ticker} +{delta} pts ({prev_score} → {score})"
            _save_alert(ticker, "SCORE_JUMP", prev_score, score, msg)
            return msg
        elif delta <= -delta_threshold:
            msg = f"{ticker} {delta} pts ({prev_score} → {score})"
            _save_alert(ticker, "SCORE_DROP", prev_score, score, msg)
            return msg

    return None


# ── Couche 2 — Health check ───────────────────────────────────────────────

def health_check():
    """Vérifie que le scorer fonctionne et que yfinance répond."""
    logger.info("Health check AlphaBrief")
    issues = []
    results = {}

    # 1) SQLite accessible
    try:
        tickers = _get_watchlist()
        results["db"] = {"ok": True, "watchlist_count": len(tickers)}
    except Exception as e:
        results["db"] = {"ok": False, "error": str(e)}
        issues.append(f"🔴 SQLite inaccessible : {e}")

    # 2) yfinance test (ticker rapide)
    t0 = time.monotonic()
    try:
        import yfinance as yf
        data = yf.Ticker("AAPL").info
        latency_ms = (time.monotonic() - t0) * 1000
        yf_ok = data is not None and "symbol" in data
        results["yfinance"] = {"ok": yf_ok, "latency_ms": round(latency_ms)}
        if not yf_ok:
            issues.append("🔴 yfinance ne retourne pas de données")
    except Exception as e:
        latency_ms = (time.monotonic() - t0) * 1000
        results["yfinance"] = {"ok": False, "latency_ms": round(latency_ms), "error": str(e)}
        issues.append(f"🔴 yfinance erreur : {e}")

    # 3) FMP call counter (depuis le démarrage du process)
    try:
        from core.providers.fmp_client import get_call_count
        results["fmp"] = {"calls_since_start": get_call_count()}
    except Exception as e:
        results["fmp"] = {"error": str(e)}

    # 4) Cache freshness
    cache_files = list(CACHE_DIR.glob("*.json")) if CACHE_DIR.exists() else []
    stale_count = 0
    cutoff = datetime.now(timezone.utc) - timedelta(hours=THRESH["cache_max_age_hours"])
    for f in cache_files:
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                stale_count += 1
        except Exception:
            pass
    results["cache"] = {"total_files": len(cache_files), "stale": stale_count}
    if stale_count > len(cache_files) * 0.5 and cache_files:
        issues.append(f"🟡 {stale_count}/{len(cache_files)} fichiers cache expirés")

    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "healthy": len(issues) == 0,
        "issues": issues,
        "results": results,
    }

    _save_snapshot("health", status)
    publish_event("alphabrief:status", status)

    if issues:
        notify(
            "📊 AlphaBrief Health Check\n" + "\n".join(issues),
            Priority.INTERESTING,
            agent="alphabrief",
        )
    else:
        logger.info("Health check OK — tout est vert")

    return status


# ── Couche 3 — Rapport quotidien ──────────────────────────────────────────

def daily_report(scoring_stats: dict | None = None):
    """Rapport quotidien : scores du jour, alertes, mouvements.

    Si scoring_stats est fourni (cas scoring_and_report), une ligne 'Scoring : X/Y'
    est ajoutee en tete pour fusionner les deux notifications precedentes en une seule.
    """
    logger.info("=== RAPPORT QUOTIDIEN ===")

    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    scores = _get_today_scores(today_iso)
    alerts = _get_unread_alerts()
    tickers = _get_watchlist()

    if not scores:
        notify(
            f"📊 AlphaBrief — Aucun score pour aujourd'hui ({today_iso})",
            Priority.INFO, agent="alphabrief",
        )
        return

    scored_tickers = {s["ticker"] for s in scores}
    missing_tickers = sorted(t for t in tickers if t not in scored_tickers)

    top5 = scores[:5]
    bottom5 = scores[-5:] if len(scores) > 5 else []

    avg_score = sum(s["score"] for s in scores) / len(scores)

    lines = [f"<b>Rapport du {datetime.now().strftime('%d/%m/%Y')}</b>", ""]

    if scoring_stats:
        scoring_line = f"✅ Scoring : {scoring_stats['scored']}/{scoring_stats['total']} tickers"
        if scoring_stats.get("sb_enabled"):
            scoring_line += f" (Supabase {scoring_stats['sb_ok']} OK / {scoring_stats['sb_failed']} KO)"
        lines.append(scoring_line)

    lines.append(f"📊 Watchlist : {len(tickers)} tickers | {len(scores)} scorés aujourd'hui")
    lines.append(f"📊 Score moyen : {avg_score:.0f}/100")

    if missing_tickers:
        lines.append(f"⚠️ Manquants : {', '.join(missing_tickers)}")

    lines.append("")
    lines.append("<b>🏆 Top 5</b>")
    for s in top5:
        lines.append(f"  {s['ticker']} — {s['score']}/100")

    if bottom5:
        lines.append("")
        lines.append("<b>📉 Bottom 5</b>")
        for s in bottom5:
            lines.append(f"  {s['ticker']} — {s['score']}/100")

    if alerts:
        lines.append("")
        lines.append(f"<b>🔔 Alertes ({len(alerts)})</b>")
        for a in alerts[:10]:
            lines.append(f"  [{a['alert_type']}] {a['message']}")

    report_text = "\n".join(lines)

    report_data = {
        "date": today_iso,
        "watchlist_count": len(tickers),
        "scored_count": len(scores),
        "missing_tickers": missing_tickers,
        "avg_score": round(avg_score, 1),
        "top5": [{"ticker": s["ticker"], "score": s["score"]} for s in top5],
        "bottom5": [{"ticker": s["ticker"], "score": s["score"]} for s in bottom5],
        "unread_alerts": len(alerts),
        "scoring_stats": scoring_stats,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    report_path = REPORTS_DIR / f"report_{today_iso}.json"
    report_path.write_text(json.dumps(report_data, indent=2, ensure_ascii=False))

    notify(report_text, Priority.INFO, agent="alphabrief")
    publish_event("alphabrief:report", report_data)
    logger.info(f"Rapport envoyé — {len(scores)}/{len(tickers)} tickers, avg {avg_score:.0f}, manquants={len(missing_tickers)}")

    # Coverage alert — second message URGENT seulement si la couverture chute
    # sous 90% du watchlist. Empêche les jours à "tickers fantômes" silencieux.
    coverage = len(scores) / max(1, len(tickers))
    if coverage < 0.90:
        notify(
            f"⚠️ AlphaBrief — couverture incomplète\n"
            f"{len(scores)}/{len(tickers)} tickers scorés ({coverage*100:.0f}%)\n"
            f"Manquants : {', '.join(missing_tickers)}",
            Priority.URGENT, agent="alphabrief",
        )


def scoring_and_report():
    """Wrapper : scoring puis rapport, en un seul message Telegram."""
    stats = scoring_run()
    daily_report(scoring_stats=stats)


# ── Couche 4 — Cache cleanup ─────────────────────────────────────────────

def cache_cleanup():
    """Supprime les fichiers cache expirés."""
    logger.info("=== CACHE CLEANUP ===")
    if not CACHE_DIR.exists():
        return

    cutoff = datetime.now(timezone.utc) - timedelta(hours=THRESH["cache_max_age_hours"])
    removed = 0

    for f in CACHE_DIR.glob("*.json"):
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception as e:
            logger.warning(f"Cache cleanup — impossible de supprimer {f.name}: {e}")

    logger.info(f"Cache cleanup : {removed} fichier(s) supprimé(s)")
    if removed > 0:
        publish_event("alphabrief:cache_cleanup", {"removed": removed})


# ── Snapshots ─────────────────────────────────────────────────────────────

def _save_snapshot(kind: str, data: dict):
    ts = datetime.now().strftime("%Y%m%dT%H%M%S")
    path = SNAPSHOTS_DIR / f"{kind}_{ts}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    # Cleanup : garder les 100 derniers par type
    files = sorted(SNAPSHOTS_DIR.glob(f"{kind}_*.json"), reverse=True)
    for old in files[100:]:
        old.unlink(missing_ok=True)


# ── Stats rapides ─────────────────────────────────────────────────────────

def show_stats():
    tickers = _get_watchlist()
    scores = _get_all_scores()
    alerts = _get_unread_alerts()
    cache_files = list(CACHE_DIR.glob("*.json")) if CACHE_DIR.exists() else []

    stats = {
        "watchlist": len(tickers),
        "scored_tickers": len(scores),
        "avg_score": round(sum(s["score"] for s in scores) / len(scores), 1) if scores else 0,
        "unread_alerts": len(alerts),
        "cache_files": len(cache_files),
        "top3": [{"ticker": s["ticker"], "score": s["score"]} for s in scores[:3]],
    }
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return stats


# ── Paper MVP wrappers — never propagate to scheduler ─────────────────────

def _paper_weekly_safe():
    """Wrapper around paper_mvp.run_weekly_rebalance with lazy import + Telegram alert on crash."""
    try:
        from paper_mvp import run_weekly_rebalance
        run_weekly_rebalance()
    except Exception as e:
        logger.exception(f"paper_mvp_weekly crashed: {e}")
        try:
            notify(f"⚠️ paper_mvp_weekly crashed: {e}", Priority.URGENT, agent="alphabrief")
        except Exception:
            pass  # notification best-effort, ne pas masquer l'erreur d'origine


def _paper_nav_safe():
    """Wrapper around paper_mvp.run_daily_nav with lazy import + Telegram alert on crash."""
    try:
        from paper_mvp import run_daily_nav
        run_daily_nav()
    except Exception as e:
        logger.exception(f"paper_mvp_nav_daily crashed: {e}")
        try:
            notify(f"⚠️ paper_mvp_nav_daily crashed: {e}", Priority.URGENT, agent="alphabrief")
        except Exception:
            pass


# ── Redis command listener ────────────────────────────────────────────────

def _start_command_listener():
    """Écoute les commandes via Redis stream."""
    STREAM = "alphabrief:commands"
    GROUP = "alphabrief_workers"
    CONSUMER = "alphabrief_main"

    try:
        redis_client.xgroup_create(STREAM, GROUP)
    except Exception:
        pass

    def _listener():
        COMMANDS = {
            "alphabrief_score": scoring_and_report,
            "alphabrief_report": daily_report,
            "alphabrief_health": health_check,
            "alphabrief_stats": show_stats,
            "alphabrief_cleanup": cache_cleanup,
        }
        while True:
            try:
                redis_client.subscribe_stream(STREAM, GROUP, CONSUMER, COMMANDS)
            except Exception as e:
                logger.error(f"Command listener error: {e}")
                time.sleep(5)

    t = threading.Thread(target=_listener, daemon=True)
    t.start()
    logger.info("Redis command listener started")


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AlphaBrief Agent — Scoring & Monitoring")
    parser.add_argument("--score", action="store_true", help="Scoring immédiat de la watchlist")
    parser.add_argument("--report", action="store_true", help="Rapport quotidien immédiat")
    parser.add_argument("--health", action="store_true", help="Health check immédiat")
    parser.add_argument("--stats", action="store_true", help="Statistiques rapides")
    parser.add_argument("--cleanup", action="store_true", help="Cache cleanup immédiat")
    parser.add_argument("--daemon", action="store_true", help="Mode daemon avec scheduling")
    args = parser.parse_args()

    if args.stats:
        show_stats()
        return

    if args.score:
        scoring_and_report()
        return

    if args.report:
        daily_report()
        return

    if args.health:
        health_check()
        return

    if args.cleanup:
        cache_cleanup()
        return

    if args.daemon:
        notify("📊 AlphaBrief Agent démarré en mode daemon", Priority.INFO, agent="alphabrief")

        _start_command_listener()

        scheduler = BlockingScheduler(timezone="Europe/Paris")

        # Scoring + rapport fusionne — 7h chaque jour (un seul message Telegram)
        scheduler.add_job(scoring_and_report, "cron", hour=CRONS["scoring_hour"], minute=0, id="ab_scoring_and_report")

        # Health check — toutes les 30 min
        scheduler.add_job(health_check, "interval", minutes=CRONS["health_check_min"], id="ab_health")

        # Cache cleanup — 3h du matin
        scheduler.add_job(cache_cleanup, "cron", hour=CRONS["cache_cleanup_hour"], minute=0, id="ab_cleanup")

        # Paper MVP — explicit UTC (scheduler global tz=Europe/Paris, DST proof)
        scheduler.add_job(
            _paper_weekly_safe, "cron", day_of_week="mon", hour=14, minute=0,
            id="paper_mvp_weekly", timezone="UTC",
        )
        scheduler.add_job(
            _paper_nav_safe, "cron", day_of_week="mon-fri", hour=22, minute=0,
            id="paper_mvp_nav_daily", timezone="UTC",
        )

        try:
            logger.info(
                f"Daemon — scoring+rapport {CRONS['scoring_hour']}h (fusionnes), "
                f"health /{CRONS['health_check_min']}min, cleanup {CRONS['cache_cleanup_hour']}h, "
                f"paper_mvp lun 14h UTC + nav lun-ven 22h UTC"
            )
            # Health check immédiat au démarrage
            health_check()
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("AlphaBrief Agent arrêté")
        return

    # Par défaut : scoring + rapport fusionnes en un seul message
    scoring_and_report()


if __name__ == "__main__":
    main()
