from flask import Blueprint, render_template, jsonify

from core.bitcoin.btc_buy_signal_analyzer import (
    get_buy_signal_analysis,
    BTCBuySignalInputs,
    calculate_buy_signal_score
)

bp = Blueprint('bitcoin', __name__, url_prefix='/bitcoin')


@bp.route('/')
def index():
    """Page principale d'analyse Bitcoin."""
    result = get_buy_signal_analysis()
    return render_template('bitcoin.html', result=result)


@bp.route('/api/analysis')
def api_analysis():
    """API endpoint pour obtenir l'analyse Bitcoin en JSON."""
    result = get_buy_signal_analysis()

    # Nettoyer le résultat pour JSON (enlever les objets non sérialisables)
    clean_result = {
        'score': result.get('score'),
        'recommendation': result.get('recommendation'),
        'recommendation_color': result.get('recommendation_color'),
        'recommendation_message': result.get('recommendation_message'),
        'indicators_available': result.get('indicators_available'),
        'indicators_total': result.get('indicators_total'),
        'indicators': {}
    }

    for name, data in result.get('indicators', {}).items():
        clean_result['indicators'][name] = {
            'score': data.get('score'),
            'signal': data.get('signal')
        }

    return jsonify(clean_result)


@bp.route('/api/refresh')
def api_refresh():
    """Force un rafraîchissement de l'analyse."""
    result = get_buy_signal_analysis()
    return jsonify({
        'success': result.get('score') is not None,
        'score': result.get('score'),
        'recommendation': result.get('recommendation')
    })
