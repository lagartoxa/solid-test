"""
Flask application factory.
"""

from flask_openapi3 import Info, OpenAPI

from app.cli import register_cli
from app.config import Config
from app.db.session import init_db

API_INFO = Info(title="Shop Payments API", version="1.0.0")


def create_app(config: type[Config] = Config) -> OpenAPI:
    """
    Create and configure the Flask application.

    OpenAPI is a Flask subclass that builds the OpenAPI spec from the routes
    and their Pydantic schemas.

    Args:
        config: Configuration class to load

    Returns:
        Flask application
    """
    app = OpenAPI(__name__, info=API_INFO, doc_prefix="/docs")
    app.config.from_object(config)

    init_db(app)
    register_cli(app)
    _serve_swagger_on_docs_index(app)

    return app


def _serve_swagger_on_docs_index(app: OpenAPI) -> None:
    """
    Show Swagger UI at /docs.

    By default /docs lists the installed doc UIs and Swagger lives at
    /docs/swagger. Swagger is the only UI we use, so /docs serves it directly.
    """
    app.view_functions["openapi.openapi"] = app.view_functions["swagger.swagger"]
