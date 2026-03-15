from flask import Blueprint, render_template, redirect, url_for, flash, request
from app.storage import JsonStore
from utils.ticker_utils import normalize_ticker, validate_ticker
from app.routes.watchlist import get_latest_scores

bp = Blueprint('pools', __name__, url_prefix='/pools')

POOL_COLORS = [
    ('#6366f1', 'Indigo'),
    ('#a78bfa', 'Violet'),
    ('#10b981', 'Vert'),
    ('#f59e0b', 'Ambre'),
    ('#ef4444', 'Rouge'),
    ('#3b82f6', 'Bleu'),
    ('#ec4899', 'Rose'),
    ('#14b8a6', 'Teal'),
]


@bp.route('/')
def index():
    pools = JsonStore.get_pools()
    pools_data = []
    for pool in pools:
        tickers = JsonStore.get_pool_tickers(pool['id'])
        scores = get_latest_scores(tickers)
        names = JsonStore.get_ticker_names(tickers)
        pools_data.append({
            'pool': pool,
            'tickers': tickers,
            'scores': scores,
            'names': names,
        })
    return render_template('pools.html', pools_data=pools_data, colors=POOL_COLORS)


@bp.route('/create', methods=['POST'])
def create():
    name = request.form.get('name', '').strip()
    color = request.form.get('color', '#6366f1')
    if not name:
        flash("Le nom du pool est requis.", "error")
        return redirect(url_for('pools.index'))
    pool_id = JsonStore.create_pool(name, color)
    if pool_id:
        flash(f"Pool « {name} » créé.", "success")
    else:
        flash(f"Un pool nommé « {name} » existe déjà.", "error")
    return redirect(url_for('pools.index'))


@bp.route('/<int:pool_id>/delete', methods=['POST'])
def delete(pool_id):
    if JsonStore.delete_pool(pool_id):
        flash("Pool supprimé.", "success")
    else:
        flash("Pool introuvable.", "error")
    return redirect(url_for('pools.index'))


@bp.route('/<int:pool_id>/add', methods=['POST'])
def add_ticker(pool_id):
    raw = request.form.get('ticker', '').strip()
    if not raw:
        flash("Veuillez entrer un ticker.", "error")
        return redirect(url_for('pools.index'))
    ticker = normalize_ticker(raw)
    try:
        is_valid, msg = validate_ticker(ticker)
        if not is_valid:
            flash(f"Ticker invalide : {msg}", "error")
            return redirect(url_for('pools.index'))
    except Exception as e:
        flash(f"Erreur de validation : {str(e)}", "error")
        return redirect(url_for('pools.index'))
    if JsonStore.add_ticker_to_pool(pool_id, ticker):
        flash(f"{ticker} ajouté au pool.", "success")
    else:
        flash(f"{ticker} est déjà dans ce pool.", "info")
    return redirect(url_for('pools.index'))


@bp.route('/<int:pool_id>/remove/<ticker>', methods=['POST'])
def remove_ticker(pool_id, ticker):
    if JsonStore.remove_ticker_from_pool(pool_id, ticker):
        flash(f"{ticker} retiré du pool.", "success")
    else:
        flash("Ticker introuvable dans ce pool.", "error")
    return redirect(url_for('pools.index'))
