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
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from apscheduler.schedulers.blocking import BlockingScheduler

from alfred.shared.config import cfg
from alfred.shared.logger import get_logger
from alfred.shared.telegram import notify, Priority
from alfred.shared.redis_client import redis_client, publish_event
from alfred.shared.heartbeat import publish_heartbeat
from core.providers.sage_advisor import generate_daily_advice
from core.scoring import bands

logger = get_logger("alphabrief")


def _ab_heartbeat() -> None:
    """Battement normalisé découplé (30s), même au repos entre les jobs métier."""
    publish_heartbeat(
        project="alphabrief", agent="alphabrief",
        status="idle", health=100,
        kpis={},
        last_event="daemon actif",
        layer="metier", cadence=30,
    )

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
        # `strong_buy_score` n'est plus une valeur libre : c'est la borne de la
        # bande « Exceptionnel » du barème unique (core/scoring/bands.py), soit
        # le p95 de la distribution réelle. Elle vivait ici en double, ce qui
        # avait laissé le daemon alerter « Score exceptionnel » sur des titres
        # que le backend étiquetait « Modéré ».
        "strong_buy_score": bands.STRONG_BUY_MIN,
        "cache_max_age_hours": 48,
    },
    "crons": {
        "scoring_hour": 7,
        "report_hour": 9,
        "health_check_min": 30,
        "cache_cleanup_hour": 3,
        "sage_hour": 8,
        # Phase du cycle économique : avant le scoring, pour que le rapport du
        # jour et l'écran Pixel Office lisent une phase fraîche. Le détecteur
        # cache 24 h de son côté, ce passage ne coûte donc qu'un run par jour.
        "cycle_hour": 6,
    },
}


def _load_config() -> dict:
    """Config du daemon, fusionnée sur les défauts.

    La fusion (et pas un simple `return json.loads(...)`) permet d'ajouter une
    clé à DEFAULT_CONFIG sans casser au démarrage sur un config.json plus ancien
    qui ne la connaît pas — un fichier écrit en mai ne doit pas empêcher le
    daemon de lire une option ajoutée en septembre.
    """
    merged = {k: dict(v) if isinstance(v, dict) else v for k, v in DEFAULT_CONFIG.items()}
    if CONFIG_PATH.exists():
        try:
            stored = json.loads(CONFIG_PATH.read_text())
        except Exception:
            stored = {}
        for section, values in stored.items():
            if isinstance(values, dict) and isinstance(merged.get(section), dict):
                merged[section].update(values)
            else:
                merged[section] = values
    else:
        CONFIG_PATH.write_text(json.dumps(merged, indent=2))
    return merged


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
    # Dual-write Postgres local : import isolé, une base indisponible ne doit
    # pas emporter le scoring SQLite avec elle.
    try:
        from core.storage.writer import write_score as pg_write_score
    except Exception as e:
        logger.error(f"writer import failed — Postgres dual-write disabled: {e}")
        pg_write_score = None

    try:
        from core.providers.events_yf import sync_events_for as sb_sync_events
    except Exception as e:
        logger.error(f"events_yf import failed — ticker_events sync disabled: {e}")
        sb_sync_events = None

    logger.info(f"{len(tickers)} tickers à scorer")
    publish_event("alphabrief:scoring_started", {"count": len(tickers)})

    scored = 0
    pg_ok = 0
    pg_failed = 0
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
                "db": "skipped",
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

                # Dual-write Postgres — isolé par ticker
                if pg_write_score is not None:
                    try:
                        ok = pg_write_score(ticker, card)
                        if ok:
                            pg_ok += 1
                            log_row["db"] = "ok"
                        else:
                            pg_failed += 1
                            log_row["db"] = "failed"
                    except Exception as pg_err:
                        pg_failed += 1
                        log_row["db"] = f"error: {pg_err}"
                        logger.error(f"Postgres write {ticker}: {pg_err}")

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
    if pg_write_score is not None:
        summary += f" | Base: {pg_ok} OK / {pg_failed} KO"
    summary += f" | FMP calls: {fmp_calls}"
    if alerts_generated:
        summary += f"\n🔔 {len(alerts_generated)} alerte(s) :"
        for a in alerts_generated:
            summary += f"\n  {a}"

    logger.info(summary)
    publish_event("alphabrief:scoring_done", {
        "scored": scored, "total": len(tickers),
        "db_ok": pg_ok, "db_failed": pg_failed,
        "alerts": len(alerts_generated),
        "fmp_calls": fmp_calls,
    })
    return {
        "scored": scored,
        "total": len(tickers),
        "db_ok": pg_ok,
        "db_failed": pg_failed,
        "db_enabled": pg_write_score is not None,
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

    # 3) FMP — compteur d'appels ET état du coupe-circuit.
    # Le compteur seul ne disait rien d'utile : il montait joyeusement pendant
    # que chaque appel se faisait refuser en 429. Le plan FMP est resté épuisé
    # des mois sans que le health check ne le signale, et les fondamentaux
    # manquants ont comprimé tous les scores pendant ce temps.
    try:
        from core.providers.fmp_client import get_call_count, plan_exhausted, fmp_get
        # Le coupe-circuit démarre fermé dans un process neuf : sans sonde, la
        # panne resterait invisible jusqu'au scoring de 7h. Une requête toutes
        # les 30 min au plus (aucune quand le circuit est déjà ouvert), et si
        # elle échoue elle ouvre le circuit — le scoring qui suit y gagne.
        if not plan_exhausted():
            fmp_get("profile", {"symbol": "AAPL"}, cache=False)
        exhausted = plan_exhausted()
        results["fmp"] = {
            "calls_since_start": get_call_count(),
            "plan_exhausted": exhausted,
        }
        # Volontairement PAS ajouté à `issues` : `issues` déclenche une
        # notification Telegram à chaque passage, soit toutes les 30 min. Or le
        # quota FMP épuisé est un état stable et sans conséquence depuis que
        # yfinance couvre tous les champs du scoring — le signaler en boucle
        # apprendrait surtout à ignorer les health checks. L'information reste
        # lisible dans le payload, le snapshot et la carte Santé du cockpit.
        if exhausted:
            logger.info("FMP : quota du plan atteint — fondamentaux via yfinance")
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
        if scoring_stats.get("db_enabled"):
            scoring_line += f" (Base {scoring_stats['db_ok']} OK / {scoring_stats['db_failed']} KO)"
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


def verifier_resultat():
    """Vérifie que le travail a PRODUIT quelque chose, pas que les outils vivent.

    health_check() teste que SQLite s'ouvre, que yfinance répond, que le cache
    est frais. C'est utile, mais ça ne dit rien du seul sujet qui compte : le
    scoring a-t-il écrit ? Entre le 25 et le 29 juillet, score_history a reçu
    5, 6, 6 puis 5 lignes pour une watchlist de 34 tickers — 85 % du travail ne
    se faisait pas — et le health check a répondu « tout est vert » toutes les
    trente minutes pendant ces quatre jours.

    D'où l'inversion : ici on ne notifie QUE si quelque chose manque. Le
    silence redevient une information au lieu d'être un bruit de fond.
    """
    from core.storage import db

    logger.info("=== VERIFICATION DU RESULTAT ===")
    anomalies: list[str] = []

    # 1. Le scoring du jour a-t-il couvert la watchlist ?
    try:
        attendus = {t.upper() for t in _get_watchlist()}
        ecrits = {
            r["ticker"].upper()
            for r in db.query(
                "SELECT DISTINCT ticker FROM score_history "
                " WHERE scored_at >= date_trunc('day', now())"
            )
        }
        manquants = attendus - ecrits
        if attendus and len(ecrits & attendus) < len(attendus) * 0.9:
            apercu = ", ".join(sorted(manquants)[:8])
            suite = f" (+{len(manquants) - 8})" if len(manquants) > 8 else ""
            anomalies.append(
                f"Scoring incomplet : {len(ecrits & attendus)}/{len(attendus)} "
                f"tickers écrits.\nManquants : {apercu}{suite}"
            )
    except Exception as e:
        anomalies.append(f"Impossible de vérifier le scoring du jour : {e}")

    # 2. Une carte figée depuis plus de 48 h est une carte morte.
    try:
        perimes = db.query(
            "SELECT ticker, EXTRACT(EPOCH FROM (now() - computed_at))/3600 AS h "
            "  FROM ticker_scores WHERE computed_at < now() - interval '48 hours' "
            " ORDER BY computed_at LIMIT 10"
        )
        if perimes:
            pire = perimes[0]
            anomalies.append(
                f"{len(perimes)} score(s) figé(s) depuis plus de 48 h — "
                f"le pire : {pire['ticker']} ({int(pire['h'])} h)"
            )
    except Exception as e:
        anomalies.append(f"Impossible de vérifier la fraîcheur des scores : {e}")

    # 3. Saisie du patrimoine périmée.
    #    Ne se déclenche que sur les supports DÉJÀ renseignés au moins une fois :
    #    avant la première saisie, il n'y a rien à relancer, et une alerte
    #    quotidienne sur un écran qui n'existe pas encore serait du bruit pur.
    try:
        vieux = db.query(
            "SELECT nom, anciennete_jours FROM v_support_dernier_snapshot "
            " WHERE anciennete_jours > 10 ORDER BY anciennete_jours DESC"
        )
        if vieux:
            detail = ", ".join(f"{v['nom']} ({v['anciennete_jours']} j)" for v in vieux)
            anomalies.append(f"Patrimoine à mettre à jour : {detail}")
    except Exception as e:
        logger.warning(f"verification patrimoine ignoree : {e}")

    if not anomalies:
        logger.info("Verification du resultat : tout a bien ete produit")
        return

    for a in anomalies:
        logger.error(f"ANOMALIE — {a}")
    try:
        notify(
            "<b>AlphaBrief — le travail n'a pas produit ce qu'il devait</b>\n\n"
            + "\n\n".join(anomalies),
            priority=Priority.URGENT,
            agent="alphabrief",
        )
    except Exception as e:
        logger.error(f"Alerte Telegram impossible : {e}")


def scoring_and_report():
    """Wrapper : scoring, rapport, puis vérification de ce qui a été produit."""
    stats = scoring_run()
    daily_report(scoring_stats=stats)
    try:
        verifier_resultat()
    except Exception as e:
        # La vérification ne doit jamais emporter le scoring qu'elle observe.
        logger.error(f"Verification du resultat en echec : {e}")


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


# ── Sage — conseil quotidien, lecture seule ─────────────────────────────────

def _local_get_json(path: str) -> dict | None:
    """GET local sur l'API Pixel Office (127.0.0.1:4300, non authentifié pour
    les routes read-only). Retourne None si l'API est indisponible plutôt que
    de faire tomber le job appelant."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:4300{path}", timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        logger.warning(f"Sage: GET {path} failed: {e}")
        return None


def refresh_economic_cycle() -> dict | None:
    """Rafraîchit la phase du cycle économique mondial.

    Le détecteur (core/bitcoin/cycle_detector.py) existait depuis mars mais
    n'était appelé par rien : l'app Flask qui l'affichait a été supprimée au
    pivot, et son cache est resté figé au 2026-02-28. Ce job le remet en
    service et c'est le SEUL producteur de la donnée — l'API Pixel Office se
    contente de lire le JSON, sans jamais lancer de Python dans la boucle
    d'événements (un execSync y gèle l'API entière).

    Silencieux par conception : une phase indisponible n'est pas un incident,
    l'écran affiche simplement la dernière connue avec sa date.
    """
    from core.bitcoin.cycle_detector import detect_economic_phase

    try:
        result = detect_economic_phase(force_refresh=True)
    except Exception as e:
        logger.warning(f"cycle économique — détection échouée : {e}")
        return None

    if result.get("error"):
        logger.warning(f"cycle économique — {result['error']}")
        return None

    logger.info(
        f"cycle économique : {result.get('phase_label')} "
        f"(confiance {result.get('confidence')}%, "
        f"{len(result.get('indicators') or {})} indicateurs)"
    )
    publish_event("alphabrief:cycle_detected", {
        "phase": result.get("phase"),
        "confidence": result.get("confidence"),
    })
    return result


def sage_daily_advice() -> None:
    """Message Telegram quotidien de Sage — conseil uniquement, aucune
    écriture, aucune exécution. Silencieux (pas de message) si une source de
    données ou la génération LLM échoue : jamais de message vide/cassé."""
    patrimoine = _local_get_json("/api/patrimoine")
    if not patrimoine:
        logger.warning("Sage: pas de données patrimoine, message du jour annulé")
        return
    agent_pref = _local_get_json("/api/alphabrief/agent") or {"agent": "sage", "risk": 3}

    text = generate_daily_advice(patrimoine, agent_pref)
    if not text:
        logger.warning("Sage: génération du conseil du jour échouée, rien envoyé")
        return

    notify(text, Priority.INFO, agent="sage")
    logger.info("Sage: conseil du jour envoyé")


# ── Main ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="AlphaBrief Agent — Scoring & Monitoring")
    parser.add_argument("--score", action="store_true", help="Scoring immédiat de la watchlist")
    parser.add_argument("--report", action="store_true", help="Rapport quotidien immédiat")
    parser.add_argument("--health", action="store_true", help="Health check immédiat")
    parser.add_argument("--stats", action="store_true", help="Statistiques rapides")
    parser.add_argument("--cleanup", action="store_true", help="Cache cleanup immédiat")
    parser.add_argument("--sage", action="store_true", help="Conseil Sage immédiat (test)")
    parser.add_argument("--cycle", action="store_true", help="Détection immédiate de la phase du cycle économique")
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

    if args.sage:
        sage_daily_advice()
        return

    if args.cycle:
        r = refresh_economic_cycle()
        if r:
            print(f"{r['phase_label']} — confiance {r['confidence']}%")
            for k, v in (r.get("indicators") or {}).items():
                print(f"  {v['name']:<32} {v['vote_label']:<16} {v['signal']}")
        else:
            print("phase indisponible")
        return

    if args.daemon:
        notify("📊 AlphaBrief Agent démarré en mode daemon", Priority.INFO, agent="alphabrief")

        _start_command_listener()

        # Barème de notation exporté au boot : l'API Pixel Office lit ce JSON
        # plutôt que de redéclarer ses seuils. Régénéré à chaque démarrage pour
        # qu'une modification de bands.py se propage au simple `pm2 restart`.
        try:
            bands.export()
        except Exception as e:
            logger.warning(f"export du barème échoué : {e}")

        scheduler = BlockingScheduler(timezone="Europe/Paris")

        # Scoring + rapport fusionne — 7h chaque jour (un seul message Telegram)
        scheduler.add_job(scoring_and_report, "cron", hour=CRONS["scoring_hour"], minute=0, id="ab_scoring_and_report")

        # Health check — toutes les 30 min
        scheduler.add_job(health_check, "interval", minutes=CRONS["health_check_min"], id="ab_health")

        # Cache cleanup — 3h du matin
        scheduler.add_job(cache_cleanup, "cron", hour=CRONS["cache_cleanup_hour"], minute=0, id="ab_cleanup")

        # Cycle économique — 6h, avant le scoring : le rapport du jour et
        # l'écran Pixel Office lisent ainsi une phase du matin, pas de la veille.
        scheduler.add_job(refresh_economic_cycle, "cron", hour=CRONS.get("cycle_hour", 6), minute=0, id="ab_cycle")

        # Sage — conseil quotidien, 8h (après le scoring de 7h)
        scheduler.add_job(sage_daily_advice, "cron", hour=CRONS.get("sage_hour", 8), minute=0, id="ab_sage_advice")

        # Heartbeat normalisé (modèle projet) — 30s, découplé des jobs métier.
        scheduler.add_job(_ab_heartbeat, "interval", seconds=30, id="ab_heartbeat")

        try:
            logger.info(
                f"Daemon — cycle {CRONS.get('cycle_hour', 6)}h, "
                f"scoring+rapport {CRONS['scoring_hour']}h (fusionnes), "
                f"health /{CRONS['health_check_min']}min, cleanup {CRONS['cache_cleanup_hour']}h, "
                f"sage {CRONS.get('sage_hour', 8)}h"
            )
            # Health check immédiat au démarrage
            health_check()
            _ab_heartbeat()  # battement immédiat au boot
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            logger.info("AlphaBrief Agent arrêté")
        return

    # Par défaut : scoring + rapport fusionnes en un seul message
    scoring_and_report()


if __name__ == "__main__":
    main()
