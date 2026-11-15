"""Signal Stack - Company Intelligence & Executive Briefing Engine."""
import os

from flask import Flask

from .db import init_db

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(BASE_DIR, "data", "signalstack.db")


def create_app(db_path=None):
    app = Flask(__name__)
    app.secret_key = os.environ.get("SIGNALSTACK_SECRET", "signalstack-local-dev")
    app.config["DB_PATH"] = db_path or os.environ.get("SIGNALSTACK_DB", DEFAULT_DB)
    app.config["DATA_DIR"] = os.path.join(BASE_DIR, "data")
    init_db(app.config["DB_PATH"])
    from .web import bp
    app.register_blueprint(bp)
    return app
