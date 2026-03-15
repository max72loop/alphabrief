from flask import Blueprint, redirect, url_for, flash
from app.storage import JsonStore
from utils import cache as _cache

bp = Blueprint('cache_mgmt', __name__, url_prefix='/cache')


@bp.route('/invalidate/<ticker>', methods=['POST'])
def invalidate(ticker: str):
    """Vide le cache fichier + SQLite d'un ticker, puis lance un re-score fresh."""
    ticker = ticker.upper()
    _cache.invalidate(ticker)          # supprime data/cache/TICKER_*.json
    JsonStore.invalidate_card_cache(ticker)  # supprime l'entrée card_cache SQLite
    flash(f"Cache vidé pour {ticker} — recalcul en cours…", "info")
    return redirect(url_for('scoring.score_single', ticker=ticker), code=307)
