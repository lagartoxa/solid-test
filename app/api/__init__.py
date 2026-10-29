"""
HTTP API: endpoints and error handling.
"""

from flask_openapi3 import OpenAPI

from app.api.errors import register_error_handlers
from app.api.logs import logs_bp
from app.api.payments import payments_bp, webhook_bp


def register_api(app: OpenAPI) -> None:
    """Register the endpoints and the error handlers on the app."""
    app.register_api(payments_bp)
    app.register_api(webhook_bp)
    app.register_api(logs_bp)
    register_error_handlers(app)
