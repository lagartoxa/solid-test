"""
Log endpoints: read the action log, to trace errors.

Open like the rest of this API; a real system would restrict them to the
support team (see the README).
"""

from http import HTTPStatus

from flask_openapi3 import APIBlueprint, Tag

from app.schemas.log import LogListResponse, LogPath, LogQuery, LogResponse
from app.schemas.payment import ErrorResponse
from app.services.log_service import build_log_service

logs_bp = APIBlueprint("logs", __name__, abp_tags=[Tag(name="Logs")])


@logs_bp.get(
    "/logs",
    summary="Search the logs",
    description="Filters are optional and combined; newest first.",
    responses={HTTPStatus.OK: LogListResponse},
)
def search_logs(query: LogQuery):
    logs, total = build_log_service().search_logs(query)
    page = LogListResponse(
        items=[LogResponse.model_validate(log) for log in logs],
        total=total,
        limit=query.limit,
        offset=query.offset,
    )

    return page.model_dump(mode="json"), HTTPStatus.OK


@logs_bp.get(
    "/logs/<log_id>",
    summary="Get one log",
    description="e.g. the log_id of an unexpected error response.",
    responses={HTTPStatus.OK: LogResponse, HTTPStatus.NOT_FOUND: ErrorResponse},
)
def get_log(path: LogPath):
    log = build_log_service().get_log(path.log_id)

    return LogResponse.model_validate(log).model_dump(mode="json"), HTTPStatus.OK
