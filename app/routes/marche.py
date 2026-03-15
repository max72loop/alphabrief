"""
Page "Marché" — Quoi acheter ce mois-ci ?

Recommandations de classes d'actifs basées sur la phase
du cycle économique détectée automatiquement.
Score 1-5 par phase, prix live via yfinance.
"""

from flask import Blueprint, render_template, jsonify
import json
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

bp = Blueprint('marche', __name__, url_prefix='/marche')

PHASE_FILE = Path(__file__).parent.parent.parent / 'data' / 'cycle_phase.json'

PHASE_LABELS = {
    'expansion': 'Expansion',
    'slowdown':  'Ralentissement',
    'recession': 'Récession',
    'recovery':  'Reprise',
}

PHASE_ICONS = {
    'expansion': '↑',
    'slowdown':  '~',
    'recession': '📉',
    'recovery':  '📈',
}

# Score 5 = ACHETER FORT  |  1 = ÉVITER
SCORE_META = {
    5: ('ACHETER FORT',    'buy-strong'),
    4: ('ACHETER',         'buy'),
    3: ('NEUTRE',          'neutral'),
    2: ('SOUS-PONDÉRER',   'underweight'),
    1: ('ÉVITER',          'avoid'),
}

# Mapping secteur yfinance → id de classe d'actif sur cette page
SECTOR_TO_ASSET = {
    'Technology':             'tech',
    'Communication Services': 'tech',
    'Financial Services':     'financials',
    'Financials':             'financials',
    'Consumer Cyclical':      'consumer_disc',   # non affiché seul, rattaché à tech/energy
    'Consumer Defensive':     'staples',
    'Healthcare':             'staples',          # défensif, proche staples
    'Health Care':            'staples',
    'Industrials':            'energy',
    'Basic Materials':        'materials',
    'Materials':              'materials',
    'Energy':                 'energy',
    'Utilities':              'bonds',            # défensif, proche obligations
    'Real Estate':            'realestate',
}

# Tickers connus comme crypto/fintech
CRYPTO_TICKERS = {'COIN', 'MSTR', 'HOOD', 'SOFI', 'NU', 'KLAR', 'GRAB'}

ASSET_CLASSES = [
    {
        'id':           'bitcoin',
        'name':         'Bitcoin',
        'subtitle':     'Crypto-monnaie',
        'icon':         '₿',
        'category':     'crypto',
        'proxy_ticker': 'BTC-USD',
        'phase_scores': {
            'expansion': 5,
            'slowdown':  3,
            'recession': 1,
            'recovery':  5,
        },
        'phase_reasons': {
            'expansion': 'Liquidité abondante et appétit maximal pour le risque. Phase idéale pour le Bitcoin.',
            'slowdown':  'Volatilité croissante avec les craintes de récession. Prudence recommandée.',
            'recession': 'Forte corrélation avec les actifs risqués. Pression vendeuse importante.',
            'recovery':  'Parmi les premiers actifs à rebondir. Catalyseur idéal de reprise.',
        },
    },
    {
        'id':           'tech',
        'name':         'Actions Technologiques',
        'subtitle':     'Nasdaq 100 — QQQ',
        'icon':         '💻',
        'category':     'equities',
        'proxy_ticker': 'QQQ',
        'phase_scores': {
            'expansion': 5,
            'slowdown':  3,
            'recession': 1,
            'recovery':  4,
        },
        'phase_reasons': {
            'expansion': 'Leader absolu en expansion. Revenus et multiples de valorisation en hausse.',
            'slowdown':  'Compression des multiples. Surveiller les révisions de bénéfices.',
            'recession': 'Forte contraction. Multiples réduits, révisions à la baisse.',
            'recovery':  'Fort rebond dès les premiers signes. Co-leader de la reprise.',
        },
    },
    {
        'id':           'financials',
        'name':         'Banques & Finance',
        'subtitle':     'Secteur financier — XLF',
        'icon':         '🏦',
        'category':     'equities',
        'proxy_ticker': 'XLF',
        'phase_scores': {
            'expansion': 4,
            'slowdown':  3,
            'recession': 1,
            'recovery':  4,
        },
        'phase_reasons': {
            'expansion': 'Marges nettes d\'intérêt solides. Activité crédit et M&A en hausse.',
            'slowdown':  'Mix de signaux. Taux encore élevés mais risques en hausse.',
            'recession': 'Hausse des créances douteuses et resserrement du crédit.',
            'recovery':  'Premières bénéficiaires de la normalisation du crédit.',
        },
    },
    {
        'id':           'realestate',
        'name':         'Immobilier (REIT)',
        'subtitle':     'Real Estate — VNQ',
        'icon':         'RE',
        'category':     'equities',
        'proxy_ticker': 'VNQ',
        'phase_scores': {
            'expansion': 4,
            'slowdown':  2,
            'recession': 1,
            'recovery':  5,
        },
        'phase_reasons': {
            'expansion': 'Demande locative forte. Valorisations et loyers en hausse.',
            'slowdown':  'Sensible aux taux montants. Pression sur les valorisations.',
            'recession': 'Forte correction. Défauts et vacances locatives en hausse.',
            'recovery':  'Rebond historiquement le plus fort de tous les secteurs.',
        },
    },
    {
        'id':           'energy',
        'name':         'Énergie',
        'subtitle':     'Pétrole & Gaz — XLE',
        'icon':         'NRJ',
        'category':     'equities',
        'proxy_ticker': 'XLE',
        'phase_scores': {
            'expansion': 4,
            'slowdown':  3,
            'recession': 2,
            'recovery':  4,
        },
        'phase_reasons': {
            'expansion': 'Demande mondiale forte. Prix de l\'énergie bien orientés.',
            'slowdown':  'Résilient grâce à la géopolitique et aux coupes OPEP.',
            'recession': 'Demande industrielle réduite. Prix pétroliers sous pression.',
            'recovery':  'Rebond de la demande industrielle mondiale.',
        },
    },
    {
        'id':           'gold',
        'name':         'Or',
        'subtitle':     'Métal précieux — GLD',
        'icon':         '🥇',
        'category':     'commodities',
        'proxy_ticker': 'GLD',
        'phase_scores': {
            'expansion': 2,
            'slowdown':  4,
            'recession': 5,
            'recovery':  2,
        },
        'phase_reasons': {
            'expansion': 'Peu attractif. Coût d\'opportunité élevé face aux actifs risqués.',
            'slowdown':  'Valeur refuge croissante. Inflation et incertitudes le soutiennent.',
            'recession': 'Valeur refuge ultime. Surperforme quand tout s\'effondre.',
            'recovery':  'Délaissé au profit des actifs cycliques plus attractifs.',
        },
    },
    {
        'id':           'bonds',
        'name':         'Obligations Long Terme',
        'subtitle':     'Treasuries 20+ ans — TLT',
        'icon':         'OBL',
        'category':     'bonds',
        'proxy_ticker': 'TLT',
        'phase_scores': {
            'expansion': 1,
            'slowdown':  3,
            'recession': 5,
            'recovery':  2,
        },
        'phase_reasons': {
            'expansion': 'Éviter. Les taux montent, les prix des obligations baissent.',
            'slowdown':  'Intérêt croissant. Les taux vont plafonner.',
            'recession': 'Phase idéale. La FED baisse les taux, forte appréciation.',
            'recovery':  'Pression vendeuse avec la remontée des taux.',
        },
    },
    {
        'id':           'staples',
        'name':         'Consommation Défensive',
        'subtitle':     'Consumer Staples — XLP',
        'icon':         'Def',
        'category':     'equities',
        'proxy_ticker': 'XLP',
        'phase_scores': {
            'expansion': 2,
            'slowdown':  4,
            'recession': 5,
            'recovery':  2,
        },
        'phase_reasons': {
            'expansion': 'Sous-performe en expansion. Préférer les secteurs cycliques.',
            'slowdown':  'Rotation défensive. Stabilité et dividendes appréciés.',
            'recession': 'Protection maximale. La consommation de base est inélastique.',
            'recovery':  'Délaissé au profit des valeurs cycliques.',
        },
    },
    {
        'id':           'materials',
        'name':         'Matières Premières',
        'subtitle':     'Commodities — GSG',
        'icon':         '⛏️',
        'category':     'commodities',
        'proxy_ticker': 'GSG',
        'phase_scores': {
            'expansion': 3,
            'slowdown':  2,
            'recession': 1,
            'recovery':  5,
        },
        'phase_reasons': {
            'expansion': 'Demande industrielle soutient les prix. Bon en mi-expansion.',
            'slowdown':  'Affecté par la baisse de la demande industrielle mondiale.',
            'recession': 'Forte baisse. Demande mondiale effondrée.',
            'recovery':  'Rebond ultra-fort. Reprise industrielle et infrastructure.',
        },
    },
]


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

CARDS_DIR      = Path(__file__).parent.parent.parent / 'data' / 'cards'
WATCHLIST_FILE = Path(__file__).parent.parent.parent / 'data' / 'watchlist.json'
SECTOR_CACHE   = Path(__file__).parent.parent.parent / 'data' / 'sector_cache.json'


def _load_sector_cache():
    try:
        if SECTOR_CACHE.exists():
            with open(SECTOR_CACHE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _save_sector_cache(data):
    try:
        SECTOR_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with open(SECTOR_CACHE, 'w') as f:
            json.dump(data, f)
    except Exception:
        pass


def _fetch_sector(ticker, cache):
    """Retourne le secteur d'un ticker depuis cache → carte → yfinance."""
    if ticker in cache:
        return ticker, cache[ticker]
    # Depuis la carte JSON locale
    card_file = CARDS_DIR / f'{ticker}.json'
    if card_file.exists():
        try:
            with open(card_file) as f:
                d = json.load(f)
            sector = d.get('identity', {}).get('sector', '')
            if sector:
                return ticker, sector
        except Exception:
            pass
    # Depuis yfinance
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        sector = info.get('sector', '') or info.get('sectorDisp', '')
        return ticker, sector
    except Exception:
        return ticker, ''


def get_tickers_by_asset_class():
    """
    Retourne un dict {asset_class_id: [ticker, ...]} pour tous les
    tickers de la watchlist, en résolvant leurs secteurs.
    """
    try:
        if not WATCHLIST_FILE.exists():
            return {}
        with open(WATCHLIST_FILE) as f:
            tickers = json.load(f).get('tickers', [])
    except Exception:
        return {}

    cache = _load_sector_cache()
    result = {}
    updated_cache = dict(cache)

    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(_fetch_sector, t, cache): t for t in tickers}
        for fut in futs:
            ticker, sector = fut.result()
            if sector:
                updated_cache[ticker] = sector
            # Crypto overrides
            if ticker in CRYPTO_TICKERS:
                asset_id = 'bitcoin'
            else:
                asset_id = SECTOR_TO_ASSET.get(sector, '')
            if asset_id:
                result.setdefault(asset_id, []).append(ticker)

    _save_sector_cache(updated_cache)
    return result


def get_current_phase():
    try:
        if PHASE_FILE.exists():
            with open(PHASE_FILE) as f:
                data = json.load(f)
                return data.get('phase', 'expansion'), data
    except Exception:
        pass
    return 'expansion', {}


def fetch_price(ticker):
    """Retourne (price, pct_day) pour un ticker."""
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(period='5d')
        if h.empty:
            return None, None
        price = float(h['Close'].iloc[-1])
        prev  = float(h['Close'].iloc[-2]) if len(h) >= 2 else price
        pct   = ((price - prev) / prev * 100) if prev else 0
        return round(price, 2), round(pct, 2)
    except Exception:
        return None, None


def get_all_prices(tickers):
    prices = {}
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(fetch_price, t): t for t in tickers}
        for f, t in futs.items():
            p, pct = f.result()
            prices[t] = {'price': p, 'pct': pct}
    return prices


def format_price(price, ticker):
    """Format price with appropriate precision."""
    if price is None:
        return '—'
    if 'BTC' in ticker or price > 1000:
        return f'${price:,.0f}'
    return f'${price:.2f}'


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@bp.route('/')
def index():
    phase, phase_meta = get_current_phase()

    # Tickers de la watchlist par classe d'actif
    tickers_by_class = get_tickers_by_asset_class()

    # Enrichir chaque asset avec son score pour la phase actuelle
    scored = []
    for asset in ASSET_CLASSES:
        score = asset['phase_scores'].get(phase, 3)
        label, css = SCORE_META.get(score, ('NEUTRE', 'neutral'))
        scored.append({
            **asset,
            'score':            score,
            'score_label':      label,
            'score_class':      css,
            'reason':           asset['phase_reasons'].get(phase, ''),
            'watchlist_tickers': tickers_by_class.get(asset['id'], []),
        })

    scored.sort(key=lambda x: x['score'], reverse=True)
    top_asset = scored[0] if scored else None

    # Prix live
    tickers = [a['proxy_ticker'] for a in scored]
    prices  = get_all_prices(tickers)

    for asset in scored:
        p = prices.get(asset['proxy_ticker'], {})
        asset['price']        = p.get('price')
        asset['price_fmt']    = format_price(p.get('price'), asset['proxy_ticker'])
        asset['pct']          = p.get('pct')

    # Détection auto (depuis le cache)
    detection = None
    cache_file = Path(__file__).parent.parent.parent / 'data' / 'cycle_detection_cache.json'
    if cache_file.exists():
        try:
            with open(cache_file) as f:
                detection = json.load(f)
        except Exception:
            pass

    current_month = datetime.now().strftime('%B %Y').capitalize()

    return render_template(
        'marche.html',
        phase=phase,
        phase_label=PHASE_LABELS.get(phase, phase),
        phase_icon=PHASE_ICONS.get(phase, ''),
        phase_meta=phase_meta,
        scored_assets=scored,
        top_asset=top_asset,
        detection=detection,
        current_month=current_month,
    )


@bp.route('/api/refresh')
def api_refresh():
    """Force une re-détection et recharge les prix."""
    try:
        from core.bitcoin.cycle_detector import detect_economic_phase, CACHE_FILE, auto_update_phase_file
        if CACHE_FILE.exists():
            CACHE_FILE.unlink()
        auto_update_phase_file()
        result = detect_economic_phase(force_refresh=True)
        return jsonify({
            'success':    result.get('phase') is not None,
            'phase':      result.get('phase'),
            'confidence': result.get('confidence'),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
