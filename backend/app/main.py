"""FastAPI entry point.

Run locally:   uvicorn app.main:app --reload --port 8000
API docs:      http://localhost:8000/docs   (OpenAPI schema at /openapi.json)

Run with ONE worker: background jobs are kept in the memory of the process (see core/jobs.py).
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .api.routes import router
from .config import get_settings
from .core.http import close_client
from .core.jobs import get_job_manager
from .core.memory import limit_pools
from .core.products import get_product_store
from .errors import AppError, error_body
from .log import setup_logging

settings = get_settings()
setup_logging()
limit_pools()  # before any job thread starts (see core/memory.py)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    get_product_store().prune()
    log.info("SPHEREx Blink API %s — collections: %s", __version__, ", ".join(settings.sia_collections))
    yield
    get_job_manager().shutdown()
    close_client()


app = FastAPI(
    title="SPHEREx Blink API",
    version=__version__,
    description="Finds SPHEREx images of a sky position and returns aligned frames, stacks and spectra.",
    lifespan=lifespan,
)

# In production the frontend calls /api through a Vercel rewrite (same origin), so CORS only
# matters for local development and direct calls.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_log(request: Request, call_next):
    """One log line per request, and an id the user can quote when something fails."""
    request_id = uuid.uuid4().hex[:8]
    request.state.request_id = request_id
    started = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - started) * 1000
    if not request.url.path.startswith("/api/products/"):
        log.info(
            "%s %s %s → %d in %.0f ms",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
    response.headers["X-Request-ID"] = request_id
    return response


def _error_response(
    request: Request, status_code: int, body: dict, headers: dict | None = None
) -> JSONResponse:
    body = {**body, "request_id": getattr(request.state, "request_id", None)}
    return JSONResponse(status_code=status_code, content={"error": body}, headers=headers)


@app.exception_handler(AppError)
async def app_error(request: Request, exc: AppError):
    headers = {"Retry-After": str(exc.retry_after_s)} if exc.retry_after_s else None
    return _error_response(request, exc.status_code, exc.to_body(), headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    problems = [{"field": ".".join(str(p) for p in e["loc"][1:]), "problem": e["msg"]} for e in exc.errors()]
    fields = ", ".join(p["field"] for p in problems) or "request"
    body = {
        "code": "invalid_parameters",
        "message": f"Check these parameters: {fields}.",
        "detail": {"problems": problems},
    }
    return _error_response(request, 422, body)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    body = {
        "code": "not_found" if exc.status_code == 404 else "http_error",
        "message": str(exc.detail),
        "detail": {},
    }
    return _error_response(request, exc.status_code, body)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    log.exception("unhandled error on %s", request.url.path, exc_info=exc)
    return _error_response(request, 500, error_body(exc))


app.include_router(router, prefix="/api")
