"""
Logs every API request and the response sent (see ActionLogger).
"""

import time
import traceback
import uuid
from typing import Any

from flask import Flask, Response, g, request
from werkzeug.exceptions import HTTPException

from app.log.action_logger import action_logger, elapsed_ms

REQUEST_ID_HEADER = "X-Request-ID"

# Both ids make debugging easier: the request id finds every log of the
# request, the log id finds the exact row with the traceback.
UNEXPECTED_ERROR_MESSAGE = "An unexpected error happened. Log id: {request_id}/{log_id}"

# The Swagger pages and assets are not API actions.
NOT_LOGGED_PATH_PREFIXES = ("/docs",)


def register_request_logging(app: Flask) -> None:
    """Register the hooks that log every request on the app."""
    app.before_request(start_request)
    app.register_error_handler(Exception, handle_unexpected_error)
    app.after_request(log_request)


def start_request() -> None:
    """Give the request an id and start measuring its duration."""
    g.request_id = uuid.uuid4()
    g.request_started_at = time.perf_counter()


def handle_unexpected_error(error: Exception) -> Any:
    """
    Turn an unexpected error into a JSON 500 response and keep its traceback for the log.

    HTTP errors (404, 405, ...) keep Flask's default handling. The response has
    the request id and the id of the API log row, so the support team can find
    the error from what the user reports. The log id is generated here because
    the log is only saved after the response is built.
    """
    if isinstance(error, HTTPException):
        return error

    g.request_error = "".join(
        traceback.format_exception(type(error), error, error.__traceback__)
    )
    g.api_log_id = uuid.uuid4()

    return {
        "error": UNEXPECTED_ERROR_MESSAGE.format(request_id=g.request_id, log_id=g.api_log_id),
        "request_id": str(g.request_id),
        "log_id": str(g.api_log_id),
    }, 500


def log_request(response: Response) -> Response:
    """Log the request and its response, and return the request id in a header."""
    response.headers[REQUEST_ID_HEADER] = str(g.request_id)

    if not request.path.startswith(NOT_LOGGED_PATH_PREFIXES):
        action_logger.log_api_request(
            method=request.method,
            path=request.path,
            request_payload={
                "headers": dict(request.headers),
                "query": request.args.to_dict(flat=False),
                "body": _request_body(),
            },
            status_code=response.status_code,
            response_payload=_response_body(response),
            error=g.get("request_error"),
            duration_ms=elapsed_ms(g.request_started_at),
            log_id=g.get("api_log_id"),
        )

    return response


def _request_body() -> Any:
    """The request body: parsed JSON when possible, text otherwise."""
    body = request.get_json(silent=True)

    if body is None:
        body = request.get_data(as_text=True) or None

    return body


def _response_body(response: Response) -> Any:
    """The response body: parsed JSON when possible, text otherwise (not for streamed files)."""
    if response.direct_passthrough:
        return None

    if response.is_json:
        return response.get_json(silent=True)

    return response.get_data(as_text=True) or None
