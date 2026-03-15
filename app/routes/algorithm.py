from flask import Blueprint, render_template, redirect, url_for, flash, request
from app.storage import JsonStore
from core.generator import generate_card
from datetime import datetime, timezone
from typing import Dict, List, Optional

bp = Blueprint('algorithm', __name__, url_prefix='/algorithm')


def calculate_score_evolution(ticker: str) -> Dict:
    """
    Calcule l'évolution des notes pour un ticker et détermine l'action recommandée.

    Retourne:
    - current_score: Note actuelle
    - previous_score: Note précédente (si disponible)
    - evolution: Différence entre les deux notes
    - evolution_percent: Évolution en pourcentage
    - action: 'buy' (>50), 'watch' (40-50), 'sell' (<=40)
    - trend: 'up', 'down', 'stable'
    """
    history = JsonStore.get_score_history(ticker=ticker)

    if not history:
        return {
            'ticker': ticker,
            'current_score': None,
            'previous_score': None,
            'evolution': None,
            'evolution_percent': None,
            'action': None,
            'trend': None,
            'last_update': None
        }

    # Trier par date (plus récent en premier)
    history.sort(key=lambda x: x.get('date', ''), reverse=True)

    current = history[0]
    current_score = current.get('score', 0)
    last_update = current.get('date', '')

    previous_score = None
    evolution = None
    evolution_percent = None
    trend = 'stable'

    if len(history) > 1:
        previous = history[1]
        previous_score = previous.get('score', 0)
        evolution = current_score - previous_score

        if previous_score > 0:
            evolution_percent = (evolution / previous_score) * 100

        if evolution > 0:
            trend = 'up'
        elif evolution < 0:
            trend = 'down'

    # Déterminer l'action basée sur le score actuel (seuils granulaires)
    if current_score >= 65:
        action = 'strong_buy'
    elif current_score > 50:
        action = 'buy'
    elif current_score >= 40:
        action = 'watch'
    elif current_score >= 30:
        action = 'sell'
    else:
        action = 'strong_sell'

    return {
        'ticker': ticker,
        'current_score': current_score,
        'previous_score': previous_score,
        'evolution': evolution,
        'evolution_percent': evolution_percent,
        'action': action,
        'trend': trend,
        'last_update': last_update,
        'confidence': current.get('confidence', 0)
    }


@bp.route('/')
def index():
    """
    Page principale de l'algorithme.
    Affiche toutes les entreprises suivies avec leur évolution de note et action recommandée.
    """
    # Récupérer toutes les entreprises de la watchlist
    watchlist = JsonStore.get_watchlist()

    # Calculer l'évolution pour chaque ticker
    algorithms_data = []
    for ticker in watchlist:
        evolution_data = calculate_score_evolution(ticker)
        if evolution_data['current_score'] is not None:
            algorithms_data.append(evolution_data)

    # Trier par action (strong_buy > buy > watch > sell > strong_sell) puis par score décroissant
    action_priority = {'strong_buy': 0, 'buy': 1, 'watch': 2, 'sell': 3, 'strong_sell': 4}
    algorithms_data.sort(key=lambda x: (action_priority.get(x['action'], 5), -x['current_score']))

    # Statistiques globales
    stats = {
        'total': len(algorithms_data),
        'strong_buy_count': sum(1 for d in algorithms_data if d['action'] == 'strong_buy'),
        'buy_count': sum(1 for d in algorithms_data if d['action'] == 'buy'),
        'watch_count': sum(1 for d in algorithms_data if d['action'] == 'watch'),
        'sell_count': sum(1 for d in algorithms_data if d['action'] == 'sell'),
        'strong_sell_count': sum(1 for d in algorithms_data if d['action'] == 'strong_sell'),
        'trending_up': sum(1 for d in algorithms_data if d['trend'] == 'up'),
        'trending_down': sum(1 for d in algorithms_data if d['trend'] == 'down'),
    }

    return render_template('algorithm.html', algorithms_data=algorithms_data, stats=stats)


@bp.route('/add', methods=['POST'])
def add_ticker():
    """Ajoute un ticker à la watchlist et génère son score initial."""
    ticker = request.form.get('ticker', '').strip().upper()

    if not ticker:
        flash("Veuillez entrer un ticker valide.", "error")
        return redirect(url_for('algorithm.index'))

    # Ajouter à la watchlist
    added = JsonStore.add_to_watchlist(ticker)
    if not added:
        flash(f"{ticker} est déjà dans la liste.", "warning")
        return redirect(url_for('algorithm.index'))

    # Générer le score initial
    try:
        card = generate_card(ticker)
        score = card.get('scores', {}).get('potential_score')
        confidence = card.get('scores', {}).get('confidence_score')

        if score is not None:
            JsonStore.add_score_entry(ticker, score, confidence or 0)
            flash(f"{ticker} ajouté avec succès. Score initial: {score}/100", "success")
        else:
            flash(f"{ticker} ajouté mais le scoring a échoué.", "warning")
    except Exception as e:
        flash(f"{ticker} ajouté mais erreur lors du scoring: {str(e)}", "error")

    return redirect(url_for('algorithm.index'))


@bp.route('/remove/<ticker>', methods=['POST'])
def remove_ticker(ticker):
    """Retire un ticker de la watchlist."""
    removed = JsonStore.remove_from_watchlist(ticker)
    if removed:
        flash(f"{ticker} retiré de la liste.", "success")
    else:
        flash(f"{ticker} n'était pas dans la liste.", "warning")

    return redirect(url_for('algorithm.index'))


@bp.route('/refresh/<ticker>', methods=['POST'])
def refresh_score(ticker):
    """Rafraîchit le score d'un ticker."""
    try:
        card = generate_card(ticker)
        score = card.get('scores', {}).get('potential_score')
        confidence = card.get('scores', {}).get('confidence_score')

        if score is not None:
            JsonStore.add_score_entry(ticker, score, confidence or 0)
            flash(f"{ticker} rafraîchi. Nouveau score: {score}/100", "success")
        else:
            flash(f"Scoring incomplet pour {ticker}", "warning")
    except Exception as e:
        flash(f"Erreur lors du rafraîchissement de {ticker}: {str(e)}", "error")

    return redirect(url_for('algorithm.index'))


@bp.route('/refresh-all', methods=['POST'])
def refresh_all():
    """Rafraîchit tous les scores de la watchlist."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    watchlist = JsonStore.get_watchlist()
    if not watchlist:
        flash("Aucune entreprise à rafraîchir.", "info")
        return redirect(url_for('algorithm.index'))

    success_count = 0
    error_count = 0

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(generate_card, ticker): ticker for ticker in watchlist}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                card = future.result()
                score = card.get('scores', {}).get('potential_score')
                confidence = card.get('scores', {}).get('confidence_score')
                if score is not None:
                    JsonStore.add_score_entry(ticker, score, confidence or 0)
                    success_count += 1
                else:
                    error_count += 1
            except Exception:
                error_count += 1

    flash(f"Rafraîchissement terminé: {success_count} réussis, {error_count} erreurs", "success")
    return redirect(url_for('algorithm.index'))


@bp.route('/add-portfolio', methods=['POST'])
def add_portfolio():
    """Ajoute toutes les entreprises du portefeuille à la watchlist et génère leurs scores."""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    portfolio = JsonStore.get_portfolio()
    if not portfolio:
        flash("Votre portefeuille est vide.", "warning")
        return redirect(url_for('algorithm.index'))

    # Récupérer la watchlist actuelle
    current_watchlist = set(JsonStore.get_watchlist())

    # Tickers à ajouter
    tickers_to_add = [h['ticker'] for h in portfolio if h['ticker'] not in current_watchlist]

    if not tickers_to_add:
        flash("Toutes les entreprises du portefeuille sont déjà dans l'algorithme.", "info")
        return redirect(url_for('algorithm.index'))

    # Ajouter à la watchlist
    for ticker in tickers_to_add:
        JsonStore.add_to_watchlist(ticker)

    # Générer les scores en parallèle
    success_count = 0
    error_count = 0

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(generate_card, ticker): ticker for ticker in tickers_to_add}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                card = future.result()
                score = card.get('scores', {}).get('potential_score')
                confidence = card.get('scores', {}).get('confidence_score')
                if score is not None:
                    JsonStore.add_score_entry(ticker, score, confidence or 0)
                    success_count += 1
                else:
                    error_count += 1
            except Exception:
                error_count += 1

    flash(f"Portefeuille ajouté: {success_count} entreprises scorées, {error_count} erreurs", "success")
    return redirect(url_for('algorithm.index'))
