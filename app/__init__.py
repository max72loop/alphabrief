from flask import Flask
from config import Config


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Ensure data directory exists
    app.config['DATA_DIR'].mkdir(parents=True, exist_ok=True)

    # Initialize SQLite database and migrate legacy JSON data
    from app.storage.json_store import JsonStore
    JsonStore.init_db(app)

    # Register blueprints
    from app.routes import register_blueprints
    register_blueprints(app)

    # Context processor : badge alertes non lues + endpoint courant pour la nav
    @app.context_processor
    def inject_nav_context():
        from flask import request
        try:
            count = JsonStore.get_unread_count()
        except Exception:
            count = 0
        return {'unread_alerts_count': count, 'current_endpoint': request.endpoint}

    # Lancer le scheduler APScheduler
    from app.scheduler import init_scheduler
    init_scheduler(app)

    return app
