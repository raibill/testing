from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask import render_template
from flask_socketio import SocketIO

# Create database object
db = SQLAlchemy()
socketio = SocketIO(cors_allowed_origins="*")


def create_app():

    app = Flask(__name__)

    # Fix 1: config.py is outside the app folder, so import it properly
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from config import Config
    app.config.from_object(Config)

    # connect database to app
    db.init_app(app)
    socketio.init_app(app)

    # import routes
    from app.routes.session_routes import session_bp
    from app.routes.order_routes import order_bp
    from app.routes.sales_routes import sales_bp
    from app.routes.user_routes import user_bp
    from app.routes.auth_routes import bp as auth_bp
    from app.routes.dashboard_routes import bp as dashboard_bp
    from app.routes.boardroom_routes import boardroom_bp

    # Fix 2: register admin_bp INSIDE create_app, not outside
    from app.routes.admin_routes import admin_bp
    from app.routes.lounge_routes import lounge_bp

    # register routes
    app.register_blueprint(session_bp)
    app.register_blueprint(order_bp)
    app.register_blueprint(sales_bp)
    app.register_blueprint(user_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(boardroom_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(lounge_bp)

    @app.route("/")
    def home():
        return render_template("landing.html")

    return app