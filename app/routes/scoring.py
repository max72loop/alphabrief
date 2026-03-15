from flask import Blueprint, render_template, redirect, url_for, flash, request
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.storage import JsonStore
from core.generator import generate_card

bp = Blueprint('scoring', __name__, url_prefix='/scoring')


@bp.route('/score/<ticker>', methods=['POST'])
def score_single(ticker):
    """FR9: Score a single ticker."""
    ticker = ticker.upper()
    try:
        card = generate_card(ticker)
        score = card.get('scores', {}).get('potential_score')
        confidence = card.get('scores', {}).get('confidence_score')

        if score is not None:
            JsonStore.add_score_entry(ticker, score, confidence or 0)
            flash(f"{ticker} — Score: {score}/100 (confiance: {confidence}%)", "success")
        else:
            flash(f"Scoring incomplet pour {ticker}", "warning")
    except Exception as e:
        flash(f"Erreur scoring {ticker} : {str(e)}", "error")

    return redirect(url_for('detail.show', ticker=ticker))


@bp.route('/batch', methods=['POST'])
def score_batch():
    """FR10: Score all tickers in watchlist."""
    tickers = JsonStore.get_watchlist()
    if not tickers:
        flash("Watchlist vide, rien à scorer.", "info")
        return redirect(url_for('watchlist.index'))

    results = _score_tickers(tickers)
    scored = sum(1 for v in results.values() if v is not None)
    flash(f"Batch terminé : {scored}/{len(tickers)} scores générés", "success")
    return redirect(url_for('watchlist.index'))


@bp.route('/batch-portfolio', methods=['POST'])
def score_batch_portfolio():
    """Score all tickers in portfolio."""
    holdings = JsonStore.get_portfolio()
    if not holdings:
        flash("Portfolio vide, rien à scorer.", "info")
        return redirect(url_for('portfolio.index'))

    tickers = [h['ticker'] for h in holdings]
    results = _score_tickers(tickers)
    scored = sum(1 for v in results.values() if v is not None)
    flash(f"Batch terminé : {scored}/{len(tickers)} scores générés", "success")
    return redirect(url_for('portfolio.index'))


def _score_tickers(tickers):
    """Helper to score multiple tickers in parallel."""
    results = {}
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(generate_card, t): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                card = future.result()
                score = card.get('scores', {}).get('potential_score')
                confidence = card.get('scores', {}).get('confidence_score')
                if score is not None:
                    JsonStore.add_score_entry(ticker, score, confidence or 0)
                results[ticker] = score
            except Exception:
                results[ticker] = None
    return results


@bp.route('/history')
def history():
    """FR15-16: View score history."""
    ticker_filter = request.args.get('ticker', '').strip().upper()
    entries = JsonStore.get_score_history(ticker=ticker_filter or None)
    entries.sort(key=lambda e: e.get('date', ''), reverse=True)
    return render_template('history.html', entries=entries, ticker_filter=ticker_filter)
