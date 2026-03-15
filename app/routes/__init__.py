def register_blueprints(app):
    from app.routes.landing import bp as landing_bp
    from app.routes.watchlist import bp as watchlist_bp
    from app.routes.portfolio import bp as portfolio_bp
    from app.routes.scoring import bp as scoring_bp
    from app.routes.detail import bp as detail_bp
    from app.routes.bitcoin import bp as bitcoin_bp
    from app.routes.algorithm import bp as algorithm_bp
    from app.routes.cycle import bp as cycle_bp
    from app.routes.marche import bp as marche_bp
    from app.routes.alerts import bp as alerts_bp
    from app.routes.screener import bp as screener_bp
    from app.routes.cache_mgmt import bp as cache_mgmt_bp
    from app.routes.compare import bp as compare_bp
    from app.routes.pools import bp as pools_bp

    app.register_blueprint(landing_bp)
    app.register_blueprint(watchlist_bp)
    app.register_blueprint(portfolio_bp)
    app.register_blueprint(scoring_bp)
    app.register_blueprint(detail_bp)
    app.register_blueprint(bitcoin_bp)
    app.register_blueprint(algorithm_bp)
    app.register_blueprint(cycle_bp)
    app.register_blueprint(marche_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(screener_bp)
    app.register_blueprint(cache_mgmt_bp)
    app.register_blueprint(compare_bp)
    app.register_blueprint(pools_bp)
