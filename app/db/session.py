"""
Database engine and session handling.

One SQLAlchemy session per request, stored on flask.g. Repositories close it
when their with statement ends; the application context teardown closes it
again as a safety net (closing twice is harmless).
"""

from flask import Flask, current_app, g
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker


def init_db(app: Flask) -> None:
    """
    Create the engine and session factory for the app and register the teardown.

    Args:
        app: Flask application
    """
    engine = create_engine(app.config["DATABASE_URL"], pool_pre_ping=True)
    # expire_on_commit=False keeps the values of objects returned by a
    # repository after its with statement commits and closes the session.
    app.extensions["session_factory"] = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )
    app.teardown_appcontext(close_session)


def get_session() -> Session:
    """
    Get the session of the current request, creating it on first use.

    Returns:
        SQLAlchemy session
    """
    if "db_session" not in g:
        g.db_session = current_app.extensions["session_factory"]()
    return g.db_session


def close_session(exception: BaseException | None = None) -> None:
    """Close the session of the current request, if one was opened."""
    session = g.pop("db_session", None)
    if session is not None:
        session.close()
