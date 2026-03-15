from flask import Blueprint, render_template, redirect, url_for, flash, request
from app.storage import JsonStore
from utils.ticker_utils import normalize_ticker, validate_ticker

bp = Blueprint('watchlist', __name__, url_prefix='/watchlist')

_SPARK_W = 60
_SPARK_H = 20
_SPARK_POINTS = 8


def _sparkline_points(scores: list) -> str:
    """Convert a chronological list of score ints to SVG polyline points string."""
    if len(scores) < 2:
        return ""
    lo, hi = min(scores), max(scores)
    spread = hi - lo or 1
    n = len(scores)
    pts = []
    for i, s in enumerate(scores):
        x = round(i * _SPARK_W / (n - 1), 2)
        y = round(_SPARK_H - (s - lo) / spread * _SPARK_H, 2)
        pts.append(f"{x},{y}")
    return " ".join(pts)


def get_latest_scores(tickers: list) -> dict:
    """Get the latest score + sparkline for each ticker."""
    scores = {}
    for ticker in tickers:
        history = JsonStore.get_score_history(ticker=ticker)
        if not history:
            continue
        history.sort(key=lambda e: e.get('date', ''))
        latest = history[-1]
        recent = [e['score'] for e in history[-_SPARK_POINTS:]]
        scores[ticker] = {
            'score': latest.get('score'),
            'confidence': latest.get('confidence'),
            'date': latest.get('date', '')[:10],
            'spark': _sparkline_points(recent),
            'trend': ('up' if len(recent) >= 2 and recent[-1] > recent[0] else
                      'down' if len(recent) >= 2 and recent[-1] < recent[0] else 'flat'),
        }
    return scores


@bp.route('/')
def index():
    tickers = JsonStore.get_watchlist()
    scores = get_latest_scores(tickers)
    names = JsonStore.get_ticker_names(tickers)
    return render_template('watchlist.html', tickers=tickers, scores=scores, names=names)


@bp.route('/add', methods=['POST'])
def add():
    raw_ticker = request.form.get('ticker', '').strip()
    if not raw_ticker:
        flash("Veuillez entrer un ticker.", "error")
        return redirect(url_for('watchlist.index'))

    ticker = normalize_ticker(raw_ticker)

    try:
        is_valid, msg = validate_ticker(ticker)
        if not is_valid:
            flash(f"Ticker invalide : {msg}", "error")
            return redirect(url_for('watchlist.index'))
    except Exception as e:
        flash(f"Erreur de validation : {str(e)}", "error")
        return redirect(url_for('watchlist.index'))

    if JsonStore.add_to_watchlist(ticker):
        flash(f"{ticker} ajouté à la watchlist", "success")
    else:
        flash(f"{ticker} est déjà dans la watchlist", "info")

    return redirect(url_for('watchlist.index'))


@bp.route('/remove/<ticker>', methods=['POST'])
def remove(ticker):
    if JsonStore.remove_from_watchlist(ticker):
        flash(f"{ticker} retiré de la watchlist", "success")
    else:
        flash(f"{ticker} non trouvé dans la watchlist", "error")
    return redirect(url_for('watchlist.index'))
