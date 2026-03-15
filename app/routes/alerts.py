from flask import Blueprint, render_template, redirect, url_for
from app.storage import JsonStore

bp = Blueprint('alerts', __name__, url_prefix='/alerts')


@bp.route('/')
def index():
    alerts = JsonStore.get_alerts()
    return render_template('alerts.html', alerts=alerts)


@bp.route('/mark-read', methods=['POST'])
def mark_read():
    JsonStore.mark_alerts_read()
    return redirect(url_for('alerts.index'))
