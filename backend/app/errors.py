"""Errors the API can answer with. Every error leaves the server as the same JSON shape:

    {"error": {"code": "no_coverage", "message": "...", "detail": {...}}}

Raise one of these anywhere (routes, pipelines, data layer); main.py turns it into the response,
and the job manager stores it in a failed job. `code` is stable and meant for the frontend;
`message` is written for the person using the page.
"""

from typing import Any


class AppError(Exception):
    status_code: int = 500
    code: str = "internal_error"

    def __init__(
        self, message: str, *, detail: dict[str, Any] | None = None, retry_after_s: int | None = None
    ):
        super().__init__(message)
        self.message = message
        self.detail = detail or {}
        self.retry_after_s = retry_after_s

    def to_body(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "detail": self.detail}


class BadRequest(AppError):
    status_code = 400
    code = "bad_request"


class TargetNotFound(AppError):
    status_code = 404
    code = "target_not_found"


class NoCoverage(AppError):
    """SPHEREx has no images of this position (in the configured releases)."""

    status_code = 404
    code = "no_coverage"


class NotEnoughFrames(AppError):
    """Images exist, but too few could be read or cover the field."""

    status_code = 404
    code = "not_enough_frames"


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class NotBuilt(AppError):
    """The contract exists but the science behind it is not written or validated yet."""

    status_code = 501
    code = "not_implemented"


class UpstreamError(AppError):
    """An external service (IRSA, S3, CDS, ESA) failed after all retries."""

    status_code = 502
    code = "upstream_error"


class UpstreamTimeout(UpstreamError):
    status_code = 504
    code = "upstream_timeout"


class Busy(AppError):
    """Too many jobs queued on our single instance."""

    status_code = 503
    code = "busy"


def error_body(exc: BaseException) -> dict[str, Any]:
    """Body for any exception; unknown ones are hidden behind a generic message."""
    if isinstance(exc, AppError):
        return exc.to_body()
    return {
        "code": "internal_error",
        "message": "Unexpected error while processing the request.",
        "detail": {"type": type(exc).__name__},
    }
