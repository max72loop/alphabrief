import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


def run_refresh(app):
    """Job APScheduler : re-score toute la watchlist et génère des alertes."""
    with app.app_context():
        from app.storage.json_store import JsonStore
        from app.storage.supabase_writer import write_score as sb_write_score
        from core.generator import generate_card

        tickers = JsonStore.get_watchlist()
        if not tickers:
            return

        delta_threshold = app.config.get('ALERT_SCORE_DELTA', 15)
        strong_buy = app.config.get('ALERT_STRONG_BUY', 75)

        logger.info(f"Auto-refresh : {len(tickers)} ticker(s) à scorer")

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {executor.submit(generate_card, t): t for t in tickers}
            for future in as_completed(futures):
                ticker = futures[future]
                try:
                    card = future.result()
                    score = card.get('scores', {}).get('potential_score')
                    confidence = card.get('scores', {}).get('confidence_score')
                    if score is None:
                        continue

                    history = JsonStore.get_score_history(ticker=ticker)
                    prev_score = history[0]['score'] if history else None

                    JsonStore.save_cached_card(ticker, card)
                    JsonStore.add_score_entry(ticker, score, confidence or 0)
                    _check_alerts(ticker, score, prev_score, delta_threshold, strong_buy)

                    # Dual-write Supabase
                    try:
                        sb_write_score(ticker, card)
                    except Exception as sb_err:
                        logger.error(f"Supabase write {ticker}: {sb_err}")

                    logger.info(f"Auto-refresh {ticker} : {score}/100")
                except Exception as e:
                    logger.error(f"Auto-refresh {ticker} : {e}")


def _check_alerts(ticker, score, prev_score, delta_threshold, strong_buy):
    from app.storage.json_store import JsonStore

    if score >= strong_buy:
        JsonStore.add_alert(
            ticker, 'STRONG_BUY', prev_score, score,
            f"{ticker} — Score exceptionnel : {score}/100"
        )
    elif prev_score is not None:
        delta = score - prev_score
        if delta >= delta_threshold:
            JsonStore.add_alert(
                ticker, 'SCORE_JUMP', prev_score, score,
                f"{ticker} +{delta} pts ({prev_score} → {score})"
            )
        elif delta <= -delta_threshold:
            JsonStore.add_alert(
                ticker, 'SCORE_DROP', prev_score, score,
                f"{ticker} {delta} pts ({prev_score} → {score})"
            )


def init_scheduler(app):
    """Initialise APScheduler. Évite le double démarrage avec le reloader Werkzeug."""
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
    except ImportError:
        logger.warning("APScheduler non installé — alertes automatiques désactivées")
        return

    hours = app.config.get('ALERT_REFRESH_HOURS', 4)
    scheduler = BackgroundScheduler()
    scheduler.add_job(run_refresh, 'interval', hours=hours, args=[app], id='auto_refresh')
    scheduler.start()
    app.scheduler = scheduler
    logger.info(f"Scheduler démarré — refresh toutes les {hours}h")
