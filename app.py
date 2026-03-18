from flask import Flask
from config import Config
from routes.webhook import webhook_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config())

    # Register blueprints
    app.register_blueprint(webhook_bp, url_prefix="/webhook")

    return app


if __name__ == "__main__":
    application = create_app()
    application.run(
        host="0.0.0.0",
        port=5000,
        debug=application.config["DEBUG"],
    )
