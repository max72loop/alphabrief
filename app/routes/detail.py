import queue
import threading

from flask import Blueprint, Response, current_app, flash, jsonify, render_template, request
from app.storage import JsonStore
from core.generator import generate_card

bp = Blueprint('detail', __name__, url_prefix='/detail')


@bp.route('/<ticker>')
def show(ticker):
    """FR17: Show detailed page for a ticker."""
    ticker = ticker.upper()
    force_refresh = request.args.get('refresh') == '1'

    try:
        card = None if force_refresh else JsonStore.get_cached_card(ticker, max_age_hours=2)
        if card is None:
            # Renvoie immédiatement la page de chargement ; le SSE génère la carte
            return render_template('loading.html', ticker=ticker)

        score = card.get('scores', {}).get('potential_score')
        confidence = card.get('scores', {}).get('confidence_score')
        if score is not None:
            JsonStore.add_score_entry(ticker, score, confidence or 0)
            smoothed = JsonStore.get_smoothed_score(ticker)
            if smoothed is not None:
                card['scores']['smoothed_score'] = smoothed

    except Exception as e:
        flash(f"Erreur chargement {ticker} : {str(e)}", "error")
        card = None

    layout = JsonStore.get_layout(ticker)

    return render_template('detail.html', ticker=ticker, card=card, layout=layout)


@bp.route('/stream/<ticker>')
def stream(ticker):
    """SSE : génère la carte et émet les étapes de progression."""
    ticker = ticker.upper()
    app = current_app._get_current_object()
    q = queue.Queue()

    def run():
        with app.app_context():
            try:
                def cb(msg):
                    q.put(('progress', msg))

                card = generate_card(ticker, progress_callback=cb)
                JsonStore.save_cached_card(ticker, card)

                score = card.get('scores', {}).get('potential_score')
                confidence = card.get('scores', {}).get('confidence_score')
                if score is not None:
                    JsonStore.add_score_entry(ticker, score, confidence or 0)

                q.put(('done', None))
            except Exception as e:
                q.put(('error', str(e)))

    threading.Thread(target=run, daemon=True).start()

    def generate():
        while True:
            event_type, data = q.get()
            if event_type == 'progress':
                yield f"data: {data}\n\n"
            elif event_type == 'done':
                yield "event: done\ndata: ok\n\n"
                break
            else:
                yield f"event: error\ndata: {data}\n\n"
                break

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
    )


@bp.route('/save-layout', methods=['POST'])
def save_layout():
    """FR23: Save section layout via AJAX."""
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400

    ticker = data.get('ticker', '').upper()
    sections = data.get('sections', [])

    if not ticker or not sections:
        return jsonify({'error': 'Missing ticker or sections'}), 400

    JsonStore.save_layout(ticker, sections)
    return jsonify({'status': 'ok'})
