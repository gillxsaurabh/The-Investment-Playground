"""Flask Blueprint registration.

All route modules are imported and registered here.
"""


def register_blueprints(app):
    """Register all Flask blueprints with the application."""
    from routes.auth import auth_bp
    from routes.portfolio import portfolio_bp
    from routes.market import market_bp
    from routes.analysis import analysis_bp
    from routes.chat import chat_bp
    from routes.trade import trade_bp
    from routes.simulator import simulator_bp
    from routes.decision_support import decision_support_bp
    from routes.health import health_bp
    from routes.sector_research import sector_research_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(portfolio_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(trade_bp)
    app.register_blueprint(simulator_bp)
    app.register_blueprint(decision_support_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(sector_research_bp)
