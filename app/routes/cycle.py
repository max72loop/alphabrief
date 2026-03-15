from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
import json
from pathlib import Path
from datetime import datetime

bp = Blueprint('cycle', __name__, url_prefix='/cycle')

# Données des secteurs S&P 500 par phase du cycle économique (source: SPDR Americas Research)
CYCLE_DATA = {
    'recession': {
        'label': 'Récession',
        'icon': '📉',
        'description': "L'économie est caractérisée par deux trimestres successifs de PIB négatif.",
        'periods': 7,
        'note': "Consumer Staples, Utilities et Health Care ont surperformé le marché de 10 % en moyenne dans 6 des 7 récessions.",
        'sectors': [
            {'name': 'Consumer Staples',      'return': 1,   'color': 'positive'},
            {'name': 'Utilities',             'return': -2,  'color': 'neutral'},
            {'name': 'Health Care',           'return': -3,  'color': 'neutral'},
            {'name': 'Energy',                'return': -4,  'color': 'neutral'},
            {'name': 'Materials',             'return': -12, 'color': 'negative'},
            {'name': 'Consumer Discretionary','return': -12, 'color': 'negative'},
            {'name': 'Financials',            'return': -13, 'color': 'negative'},
            {'name': 'Industrials',           'return': -15, 'color': 'negative'},
            {'name': 'Technology',            'return': -20, 'color': 'negative'},
            {'name': 'Real Estate',           'return': -22, 'color': 'negative'},
        ]
    },
    'recovery': {
        'label': 'Reprise',
        'icon': '📈',
        'description': "L'activité économique reprend et l'économie recommence à croître.",
        'periods': 7,
        'note': "L'immobilier (Real Estate) a eu les meilleures performances après les périodes de contraction économique.",
        'sectors': [
            {'name': 'Real Estate',           'return': 39, 'color': 'strong'},
            {'name': 'Consumer Discretionary','return': 33, 'color': 'strong'},
            {'name': 'Materials',             'return': 29, 'color': 'positive'},
            {'name': 'Technology',            'return': 28, 'color': 'positive'},
            {'name': 'Energy',                'return': 27, 'color': 'positive'},
            {'name': 'Industrials',           'return': 27, 'color': 'positive'},
            {'name': 'Financials',            'return': 23, 'color': 'moderate'},
            {'name': 'Health Care',           'return': 21, 'color': 'moderate'},
            {'name': 'Consumer Staples',      'return': 18, 'color': 'moderate'},
            {'name': 'Utilities',             'return': 15, 'color': 'low'},
        ]
    },
    'expansion': {
        'label': 'Expansion',
        'icon': '↑',
        'description': "L'économie croît au-delà de la reprise, caractérisée par une hausse de la production, de l'emploi et des revenus.",
        'periods': 12,
        'note': "La technologie et les financières ont montré les meilleures performances, battant le marché dans 10 des 12 périodes d'expansion.",
        'sectors': [
            {'name': 'Technology',            'return': 21, 'color': 'strong'},
            {'name': 'Financials',            'return': 19, 'color': 'positive'},
            {'name': 'Real Estate',           'return': 18, 'color': 'positive'},
            {'name': 'Consumer Discretionary','return': 17, 'color': 'positive'},
            {'name': 'Energy',                'return': 16, 'color': 'positive'},
            {'name': 'Industrials',           'return': 16, 'color': 'positive'},
            {'name': 'Materials',             'return': 13, 'color': 'moderate'},
            {'name': 'Consumer Staples',      'return': 11, 'color': 'moderate'},
            {'name': 'Health Care',           'return': 11, 'color': 'moderate'},
            {'name': 'Utilities',             'return': 8,  'color': 'low'},
        ]
    },
    'slowdown': {
        'label': 'Ralentissement',
        'icon': '~',
        'description': "La croissance commence à décliner mais l'économie ne se contracte pas nécessairement.",
        'periods': 11,
        'note': "Le secteur santé est considéré comme défensif, moins sensible aux fluctuations du cycle économique.",
        'sectors': [
            {'name': 'Health Care',           'return': 15, 'color': 'positive'},
            {'name': 'Consumer Staples',      'return': 15, 'color': 'positive'},
            {'name': 'Utilities',             'return': 12, 'color': 'moderate'},
            {'name': 'Industrials',           'return': 12, 'color': 'moderate'},
            {'name': 'Financials',            'return': 14, 'color': 'moderate'},
            {'name': 'Energy',                'return': 9,  'color': 'low'},
            {'name': 'Materials',             'return': 7,  'color': 'low'},
            {'name': 'Consumer Discretionary','return': 6,  'color': 'low'},
            {'name': 'Technology',            'return': 10, 'color': 'low'},
            {'name': 'Real Estate',           'return': 2,  'color': 'weak'},
        ]
    }
}

SECTOR_MAPPING = {
    'Technology':           'Technology',
    'Financial Services':   'Financials',
    'Financials':           'Financials',
    'Real Estate':          'Real Estate',
    'Consumer Cyclical':    'Consumer Discretionary',
    'Consumer Defensive':   'Consumer Staples',
    'Healthcare':           'Health Care',
    'Health Care':          'Health Care',
    'Industrials':          'Industrials',
    'Basic Materials':      'Materials',
    'Materials':            'Materials',
    'Energy':               'Energy',
    'Utilities':            'Utilities',
    'Communication Services': None,
}

NEXT_PHASE = {
    'expansion': 'slowdown',
    'slowdown':  'recession',
    'recession': 'recovery',
    'recovery':  'expansion',
}

PHASE_FILE = Path(__file__).parent.parent.parent / 'data' / 'cycle_phase.json'


def get_current_phase():
    try:
        if PHASE_FILE.exists():
            with open(PHASE_FILE) as f:
                data = json.load(f)
                return data.get('phase', 'expansion')
    except Exception:
        pass
    return 'expansion'


def get_phase_meta():
    """Retourne la phase + métadonnées (source, confidence, detected_at)."""
    try:
        if PHASE_FILE.exists():
            with open(PHASE_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {'phase': 'expansion', 'source': 'auto', 'confidence': None}


def save_current_phase(phase, source='manual'):
    PHASE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PHASE_FILE, 'w') as f:
        json.dump({
            'phase':      phase,
            'source':     source,
            'updated_at': datetime.now().isoformat(),
        }, f)


def get_watchlist_sectors():
    from app.storage import JsonStore
    cards_dir = Path(__file__).parent.parent.parent / 'data' / 'cards'
    result = {}
    try:
        tickers = JsonStore.get_watchlist()
        for ticker in tickers:
            card_file = cards_dir / f'{ticker}.json'
            if card_file.exists():
                with open(card_file) as f:
                    card = json.load(f)
                raw_sector = card.get('identity', {}).get('sector', '')
                mapped = SECTOR_MAPPING.get(raw_sector, raw_sector)
                if mapped:
                    result.setdefault(mapped, []).append(ticker)
    except Exception:
        pass
    return result


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@bp.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        phase = request.form.get('phase')
        if phase in CYCLE_DATA:
            save_current_phase(phase, source='manual')
            flash(f"Phase mise à jour manuellement : {CYCLE_DATA[phase]['label']}", 'success')
        return redirect(url_for('cycle.index'))

    # ── Auto-détection (avec cache 24 h) ──────────────
    detection = None
    try:
        from core.bitcoin.cycle_detector import detect_economic_phase, auto_update_phase_file
        auto_update_phase_file()           # met à jour PHASE_FILE si pas d'override récent
        detection = detect_economic_phase()
    except Exception:
        pass

    phase_meta       = get_phase_meta()
    current_phase    = phase_meta.get('phase', 'expansion')
    phase_source     = phase_meta.get('source', 'auto')
    watchlist_sectors = get_watchlist_sectors()

    # Résumé des 4 phases pour les cartes de sélection
    phases_summary = {}
    for key, data in CYCLE_DATA.items():
        top3 = sorted(data['sectors'], key=lambda x: x['return'], reverse=True)[:3]
        phases_summary[key] = {
            'label': data['label'],
            'icon':  data['icon'],
            'top3':  top3,
        }

    current_data = CYCLE_DATA[current_phase]

    enriched_sectors = []
    for i, sector in enumerate(current_data['sectors']):
        tickers   = watchlist_sectors.get(sector['name'], [])
        alignment = 'favorable' if i < 3 else ('neutral' if i < 7 else 'weak')
        enriched_sectors.append({**sector, 'tickers': tickers, 'rank': i + 1, 'alignment': alignment})

    max_abs = max(abs(s['return']) for s in current_data['sectors']) if current_data['sectors'] else 40

    top_sectors    = enriched_sectors[:3]
    worst_sectors  = list(reversed(enriched_sectors[-3:]))

    next_phase_key  = NEXT_PHASE[current_phase]
    next_phase_info = {
        'key':   next_phase_key,
        'label': CYCLE_DATA[next_phase_key]['label'],
        'icon':  CYCLE_DATA[next_phase_key]['icon'],
    }

    watchlist_by_alignment = {'favorable': [], 'neutral': [], 'weak': []}
    for sector in enriched_sectors:
        if sector['tickers']:
            watchlist_by_alignment[sector['alignment']].append(sector)

    return render_template(
        'cycle.html',
        current_phase=current_phase,
        current_data=current_data,
        enriched_sectors=enriched_sectors,
        phases_summary=phases_summary,
        max_abs=max_abs,
        watchlist_sectors=watchlist_sectors,
        top_sectors=top_sectors,
        worst_sectors=worst_sectors,
        next_phase_info=next_phase_info,
        watchlist_by_alignment=watchlist_by_alignment,
        detection=detection,
        phase_source=phase_source,
    )


@bp.route('/api/detect')
def api_detect():
    """Force une re-détection (supprime le cache)."""
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
            'error':      result.get('error'),
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@bp.route('/newsletter')
def newsletter():
    """Rapport hebdomadaire synthétique : phase, indicateurs, allocations, watchlist."""
    detection = None
    try:
        from core.bitcoin.cycle_detector import detect_economic_phase, auto_update_phase_file
        auto_update_phase_file()
        detection = detect_economic_phase()
    except Exception:
        pass

    phase_meta    = get_phase_meta()
    current_phase = phase_meta.get('phase', 'expansion')
    watchlist_sectors = get_watchlist_sectors()

    current_data = CYCLE_DATA[current_phase]

    enriched_sectors = []
    for i, sector in enumerate(current_data['sectors']):
        tickers   = watchlist_sectors.get(sector['name'], [])
        alignment = 'favorable' if i < 3 else ('neutral' if i < 7 else 'weak')
        enriched_sectors.append({**sector, 'tickers': tickers, 'rank': i + 1, 'alignment': alignment})

    top_sectors   = enriched_sectors[:3]
    worst_sectors = list(reversed(enriched_sectors[-3:]))

    watchlist_by_alignment = {'favorable': [], 'neutral': [], 'weak': []}
    for sector in enriched_sectors:
        if sector['tickers']:
            watchlist_by_alignment[sector['alignment']].append(sector)

    return render_template(
        'newsletter.html',
        current_phase=current_phase,
        current_data=current_data,
        enriched_sectors=enriched_sectors,
        top_sectors=top_sectors,
        worst_sectors=worst_sectors,
        watchlist_by_alignment=watchlist_by_alignment,
        detection=detection,
        generated_at=datetime.now(),
    )
