"""
Détection automatique de la phase du cycle économique mondial.

Indicateurs utilisés (tous via yfinance, sans clé API) :
  - Courbe des taux 10Y − 3M (^TNX − ^IRX)
  - Momentum S&P 500 sur 12m / 3m (SPY)
  - VIX — indice de peur (^VIX)
  - Ratio Cuivre/Or sur 6m (HG=F / GC=F)
  - Conditions de crédit HYG/IEF sur 3m
  - Momentum Euro Stoxx 50 sur 12m / 3m (^STOXX50E)
  - Momentum Nikkei 225 sur 12m / 3m (^N225)

Chaque indicateur vote pour une phase avec un poids.
La phase majoritaire (votes pondérés) est retenue.
Cache 24h dans data/cycle_detection_cache.json.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

CACHE_FILE = Path(__file__).parent.parent.parent / 'data' / 'cycle_detection_cache.json'
CACHE_TTL_HOURS = 24

PHASE_FILE = Path(__file__).parent.parent.parent / 'data' / 'cycle_phase.json'

WEIGHTS = {
    'yield_curve':        3,
    'spy_momentum':       3,
    'vix':                2,
    'copper_gold':        2,
    'credit':             1,
    'eurostoxx_momentum': 2,
    'nikkei_momentum':    1,
}

INDICATOR_NAMES = {
    'yield_curve':        'Courbe des taux (10Y − 3M)',
    'spy_momentum':       'Momentum S&P 500 (12m)',
    'vix':                'VIX — Indice de peur',
    'copper_gold':        'Ratio Cuivre / Or (6m)',
    'credit':             'Crédit haut rendement HYG (3m)',
    'eurostoxx_momentum': 'Momentum Euro Stoxx 50 (12m)',
    'nikkei_momentum':    'Momentum Nikkei 225 (12m)',
}

PHASE_LABELS = {
    'expansion': 'Expansion',
    'slowdown':  'Ralentissement',
    'recession': 'Récession',
    'recovery':  'Reprise',
}


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def _fetch(ticker, period='2y'):
    """Fetch closing prices from yfinance."""
    try:
        import yfinance as yf
        h = yf.Ticker(ticker).history(period=period)
        if h.empty:
            return None
        return h['Close'].dropna()
    except Exception:
        return None


def _momentum(series, months):
    """% change over approximately N months (21 trading days each)."""
    days = max(1, months * 21)
    start = series.iloc[-days] if len(series) > days else series.iloc[0]
    end = series.iloc[-1]
    if float(start) == 0:
        return 0.0
    return float((end / start - 1) * 100)


# ─────────────────────────────────────────────
# Individual indicator scorers
# Each returns (vote, numeric_value, signal_str, css_class)
# or (None, None, None, None) on failure.
# ─────────────────────────────────────────────

def _score_yield_curve(tnx, irx):
    if tnx is None or irx is None:
        return None, None, None, None
    try:
        t = float(tnx.iloc[-1])
        i = float(irx.iloc[-1])
        spread = round(t - i, 2)
        if spread > 1.5:
            return 'expansion', spread, f'+{spread} %', 'positive'
        elif spread > 0.3:
            return 'slowdown', spread, f'+{spread} %', 'neutral'
        elif spread > -0.5:
            return 'recession', spread, f'{spread} % (aplatissement)', 'warning'
        else:
            return 'recession', spread, f'{spread} % (inversé ⚠)', 'negative'
    except Exception:
        return None, None, None, None


def _score_index_momentum(series):
    """Generic momentum scorer for equity indices (SPY, Euro Stoxx 50, Nikkei, etc.)."""
    if series is None:
        return None, None, None, None
    try:
        m12 = _momentum(series, 12)
        m6  = _momentum(series, 6)
        m3  = _momentum(series, 3)

        if m12 > 15 and m3 > 2:
            vote, sig, cls = 'expansion', f'+{m12:.1f} % / 12m', 'positive'
        elif m12 > 5 and m6 > 0:
            vote, sig, cls = 'expansion', f'+{m12:.1f} % / 12m', 'positive'
        elif m12 > 0 and m3 < 0:
            vote, sig, cls = 'slowdown', f'+{m12:.1f} % / 12m (3m : {m3:.1f} %)', 'warning'
        elif m12 < 0 and m3 < 0:
            vote, sig, cls = 'recession', f'{m12:.1f} % / 12m', 'negative'
        elif m12 < -10 and m3 > 3:
            vote, sig, cls = 'recovery', f'{m12:.1f} % / 12m (rebond 3m : +{m3:.1f} %)', 'neutral'
        else:
            vote, sig, cls = 'slowdown', f'+{m12:.1f} % / 12m', 'neutral'

        return vote, round(m12, 1), sig, cls
    except Exception:
        return None, None, None, None


def _score_spy_momentum(spy):
    return _score_index_momentum(spy)


def _score_vix(vix):
    if vix is None:
        return None, None, None, None
    try:
        v = float(vix.iloc[-1])
        if v < 15:
            return 'expansion', v, f'{v:.1f} — bas', 'positive'
        elif v < 20:
            return 'slowdown', v, f'{v:.1f} — modéré', 'neutral'
        elif v < 28:
            return 'recession', v, f'{v:.1f} — élevé', 'warning'
        else:
            return 'recession', v, f'{v:.1f} — très élevé ⚠', 'negative'
    except Exception:
        return None, None, None, None


def _score_copper_gold(cu, au):
    if cu is None or au is None:
        return None, None, None, None
    try:
        common = cu.index.intersection(au.index)
        if len(common) < 60:
            return None, None, None, None
        ratio = cu[common] / au[common]
        t = round(_momentum(ratio, 6), 1)
        if t > 5:
            return 'expansion', t, f'+{t} % / 6m', 'positive'
        elif t > 0:
            return 'slowdown', t, f'+{t} % / 6m', 'neutral'
        elif t > -5:
            return 'slowdown', t, f'{t} % / 6m', 'warning'
        else:
            return 'recession', t, f'{t} % / 6m', 'negative'
    except Exception:
        return None, None, None, None


def _score_credit(hyg, ief):
    if hyg is None:
        return None, None, None, None
    try:
        src = hyg
        if ief is not None:
            common = hyg.index.intersection(ief.index)
            if len(common) >= 30:
                src = hyg[common] / ief[common]
        t = round(_momentum(src, 3), 1)
        if t > 2:
            return 'expansion', t, f'+{t} % / 3m', 'positive'
        elif t > -1:
            return 'slowdown', t, f'{t:+.1f} % / 3m', 'neutral'
        else:
            return 'recession', t, f'{t} % / 3m', 'negative'
    except Exception:
        return None, None, None, None


# ─────────────────────────────────────────────
# Main detection function
# ─────────────────────────────────────────────

def detect_economic_phase(force_refresh=False):
    """
    Détecte la phase du cycle économique mondial.

    Retourne un dict :
      phase          : 'expansion' | 'slowdown' | 'recession' | 'recovery' | None
      confidence     : int 0-100 (% des votes pondérés)
      detected_at    : str ISO
      indicators     : dict  (voir structure ci-dessous)
      vote_breakdown : dict  par phase
      error          : None | str
    """
    if not force_refresh:
        cached = _load_cache()
        if cached:
            return cached

    try:
        import yfinance  # noqa — just to check availability
    except ImportError:
        return _error_result('yfinance non installé (pip install yfinance)')

    # ── Fetch all data in parallel ──────────────────
    tickers = {
        'TNX':      '^TNX',
        'IRX':      '^IRX',
        'SPY':      'SPY',
        'VIX':      '^VIX',
        'copper':   'HG=F',
        'gold':     'GC=F',
        'hyg':      'HYG',
        'ief':      'IEF',
        'eurostoxx': '^STOXX50E',
        'nikkei':    '^N225',
    }
    raw = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(_fetch, v): k for k, v in tickers.items()}
        for f in as_completed(futs):
            raw[futs[f]] = f.result()

    # ── Score each indicator ────────────────────────
    scorers = [
        ('yield_curve',        _score_yield_curve(raw.get('TNX'), raw.get('IRX'))),
        ('spy_momentum',       _score_spy_momentum(raw.get('SPY'))),
        ('vix',                _score_vix(raw.get('VIX'))),
        ('copper_gold',        _score_copper_gold(raw.get('copper'), raw.get('gold'))),
        ('credit',             _score_credit(raw.get('hyg'), raw.get('ief'))),
        ('eurostoxx_momentum', _score_index_momentum(raw.get('eurostoxx'))),
        ('nikkei_momentum',    _score_index_momentum(raw.get('nikkei'))),
    ]

    votes = {'expansion': 0, 'slowdown': 0, 'recession': 0, 'recovery': 0}
    indicators = {}

    for key, (vote, value, signal, css) in scorers:
        if vote:
            votes[vote] += WEIGHTS[key]
            indicators[key] = {
                'name':         INDICATOR_NAMES[key],
                'vote':         vote,
                'vote_label':   PHASE_LABELS.get(vote, vote),
                'value':        value,
                'signal':       signal,
                'signal_class': css,
            }

    total = sum(votes.values())
    if total == 0:
        return _error_result('Aucun indicateur disponible — vérifiez la connexion')

    phase      = max(votes, key=votes.get)
    confidence = round(votes[phase] / total * 100)

    result = {
        'phase':          phase,
        'phase_label':    PHASE_LABELS.get(phase, phase),
        'confidence':     confidence,
        'detected_at':    datetime.now().isoformat(),
        'indicators':     indicators,
        'vote_breakdown': votes,
        'error':          None,
    }

    _save_cache(result)
    return result


def auto_update_phase_file():
    """
    Met à jour PHASE_FILE avec la phase auto-détectée
    seulement si la phase stockée n'a pas été définie manuellement
    au cours des dernières 12 h.
    """
    try:
        manual_override = False
        if PHASE_FILE.exists():
            with open(PHASE_FILE) as f:
                stored = json.load(f)
            if stored.get('source') == 'manual':
                ts = stored.get('updated_at', '')
                if ts:
                    updated = datetime.fromisoformat(ts)
                    if datetime.now() - updated < timedelta(hours=12):
                        manual_override = True

        if manual_override:
            return

        result = detect_economic_phase()
        if result.get('phase'):
            PHASE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(PHASE_FILE, 'w') as f:
                json.dump({
                    'phase':        result['phase'],
                    'source':       'auto',
                    'confidence':   result['confidence'],
                    'detected_at':  result['detected_at'],
                }, f)
    except Exception:
        pass


# ─────────────────────────────────────────────
# Cache helpers
# ─────────────────────────────────────────────

def _load_cache():
    try:
        if not CACHE_FILE.exists():
            return None
        with open(CACHE_FILE) as f:
            data = json.load(f)
        cached_at = datetime.fromisoformat(data['detected_at'])
        if datetime.now() - cached_at > timedelta(hours=CACHE_TTL_HOURS):
            return None
        return data
    except Exception:
        return None


def _save_cache(result):
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, 'w') as f:
            json.dump(result, f, indent=2, default=str)
    except Exception:
        pass


def _error_result(msg):
    return {
        'phase':          None,
        'phase_label':    None,
        'confidence':     0,
        'detected_at':    datetime.now().isoformat(),
        'indicators':     {},
        'vote_breakdown': {},
        'error':          msg,
    }
