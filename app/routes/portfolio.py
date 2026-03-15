from flask import Blueprint, render_template, redirect, url_for, flash, request
from app.storage import JsonStore
from utils.ticker_utils import normalize_ticker
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor

bp = Blueprint('portfolio', __name__, url_prefix='/portfolio')

# Cache des taux de change (refresh à chaque chargement de page)
_exchange_rates = {}


def get_exchange_rate(from_currency: str, to_currency: str = 'EUR') -> float:
    """Get exchange rate from one currency to EUR."""
    if from_currency == to_currency:
        return 1.0

    cache_key = f"{from_currency}{to_currency}"
    if cache_key in _exchange_rates:
        return _exchange_rates[cache_key]

    try:
        # yfinance format: USDEUR=X
        pair = f"{from_currency}{to_currency}=X"
        ticker = yf.Ticker(pair)
        rate = ticker.info.get('regularMarketPrice') or ticker.info.get('previousClose')
        if rate:
            _exchange_rates[cache_key] = float(rate)
            return float(rate)
    except Exception:
        pass

    # Fallback rates si yfinance échoue
    fallback = {
        'USDEUR': 0.92,
        'GBPEUR': 1.17,
        'JPYEUR': 0.0061,
        'CHFEUR': 1.05,
        'CADEUR': 0.68,
        'AUDEUR': 0.60,
        'HKDEUR': 0.12,
        'CNYEUR': 0.13,
        'KRWEUR': 0.00067,
        'TWDEUR': 0.028,
        'BRLEUR': 0.16,
        'MXNEUR': 0.045,
    }
    return fallback.get(cache_key, 1.0)


def get_latest_scores(tickers: list) -> dict:
    """Get the latest score for each ticker from history."""
    scores = {}
    for ticker in tickers:
        history = JsonStore.get_score_history(ticker=ticker)
        if history:
            history.sort(key=lambda e: e.get('date', ''), reverse=True)
            latest = history[0]
            scores[ticker] = {
                'score': latest.get('score'),
                'confidence': latest.get('confidence'),
                'date': latest.get('date', '')[:10]
            }
    return scores


def fetch_current_price(ticker: str) -> dict:
    """Fetch current price for a ticker."""
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}
        price = info.get('currentPrice') or info.get('regularMarketPrice')
        prev_close = info.get('previousClose')
        change_pct = None
        if price and prev_close and prev_close > 0:
            change_pct = ((price - prev_close) / prev_close) * 100
        return {
            'ticker': ticker,
            'price': price,
            'change_pct': change_pct,
            'currency': info.get('currency', 'USD')
        }
    except Exception:
        return {'ticker': ticker, 'price': None, 'change_pct': None, 'currency': None}


def enrich_holdings(holdings: list) -> tuple:
    """Enrich holdings with current prices and compute stats in EUR."""
    if not holdings:
        return [], {}

    # Clear rate cache for fresh rates
    _exchange_rates.clear()

    tickers = [h['ticker'] for h in holdings]

    # Get latest scores and company names
    scores = get_latest_scores(tickers)
    names = JsonStore.get_ticker_names(tickers)

    # Fetch prices in parallel
    prices = {}
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = list(executor.map(fetch_current_price, tickers))
        for r in results:
            prices[r['ticker']] = r

    # Collect unique currencies and fetch rates
    currencies = set(r.get('currency') for r in prices.values() if r.get('currency'))
    rates = {}
    for curr in currencies:
        if curr and curr != 'EUR':
            rates[curr] = get_exchange_rate(curr, 'EUR')
    rates['EUR'] = 1.0

    # Enrich each holding
    enriched = []
    total_invested = 0
    total_value = 0
    total_pnl = 0

    for h in holdings:
        ticker = h['ticker']
        quantity = h.get('quantity', 0)
        buy_price_eur = h.get('buy_price', 0)  # User enters price in EUR
        current = prices.get(ticker, {})
        current_price_native = current.get('price')
        currency = current.get('currency') or 'USD'

        # Convert current price to EUR
        rate = rates.get(currency, 1.0)
        current_price_eur = current_price_native * rate if current_price_native else None

        invested = quantity * buy_price_eur if quantity and buy_price_eur else 0
        value = quantity * current_price_eur if quantity and current_price_eur else 0
        pnl = value - invested if invested > 0 else 0
        pnl_pct = (pnl / invested * 100) if invested > 0 else 0

        # Get score data
        score_data = scores.get(ticker, {})

        enriched.append({
            'ticker': ticker,
            'name': names.get(ticker),
            'quantity': quantity,
            'buy_price': buy_price_eur,
            'current_price': current_price_eur,
            'current_price_native': current_price_native,
            'currency': currency,
            'rate': rate,
            'change_pct': current.get('change_pct'),
            'invested': invested,
            'value': value,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'added_at': h.get('added_at'),
            'score': score_data.get('score'),
            'confidence': score_data.get('confidence'),
            'score_date': score_data.get('date')
        })

        total_invested += invested
        total_value += value
        total_pnl += pnl

    total_pnl_pct = (total_pnl / total_invested * 100) if total_invested > 0 else 0

    stats = {
        'total_invested': total_invested,
        'total_value': total_value,
        'total_pnl': total_pnl,
        'total_pnl_pct': total_pnl_pct,
        'positions': len(holdings)
    }

    return enriched, stats


@bp.route('/')
def index():
    holdings = JsonStore.get_portfolio()
    enriched, stats = enrich_holdings(holdings)
    return render_template('portfolio.html', holdings=enriched, stats=stats)


@bp.route('/add', methods=['POST'])
def add():
    raw_ticker = request.form.get('ticker', '').strip()
    if not raw_ticker:
        flash("Veuillez entrer un ticker.", "error")
        return redirect(url_for('portfolio.index'))

    ticker = normalize_ticker(raw_ticker)

    # Parse quantity and price (price in EUR)
    try:
        quantity = float(request.form.get('quantity', 0) or 0)
    except ValueError:
        quantity = 0
    try:
        buy_price = float(request.form.get('buy_price', 0) or 0)
    except ValueError:
        buy_price = 0

    if JsonStore.add_to_portfolio(ticker, quantity, buy_price):
        flash(f"{ticker} ajouté au portefeuille", "success")
    else:
        flash(f"{ticker} est déjà dans le portefeuille", "info")
    return redirect(url_for('portfolio.index'))


@bp.route('/update/<ticker>', methods=['POST'])
def update(ticker):
    """Update quantity and buy price for a holding."""
    ticker = ticker.upper()
    try:
        quantity = float(request.form.get('quantity', 0) or 0)
    except ValueError:
        quantity = 0
    try:
        buy_price = float(request.form.get('buy_price', 0) or 0)
    except ValueError:
        buy_price = 0

    if JsonStore.update_holding(ticker, quantity, buy_price):
        flash(f"{ticker} mis à jour", "success")
    else:
        flash(f"{ticker} non trouvé", "error")
    return redirect(url_for('portfolio.index'))


@bp.route('/remove/<ticker>', methods=['POST'])
def remove(ticker):
    if JsonStore.remove_from_portfolio(ticker):
        flash(f"{ticker} retiré du portefeuille", "success")
    else:
        flash(f"{ticker} non trouvé", "error")
    return redirect(url_for('portfolio.index'))


@bp.route('/transfer/<ticker>', methods=['POST'])
def transfer(ticker):
    """Transfer ticker from watchlist to portfolio."""
    ticker = ticker.upper()
    if JsonStore.add_to_portfolio(ticker):
        JsonStore.remove_from_watchlist(ticker)
        flash(f"{ticker} transféré vers le portefeuille", "success")
    else:
        flash(f"{ticker} est déjà dans le portefeuille", "info")
    return redirect(url_for('portfolio.index'))
