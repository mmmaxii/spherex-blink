"""FastAPI entry point.

Run locally:   uvicorn app.main:app --reload --port 8000
API docs:      http://localhost:8000/docs   (OpenAPI schema at /openapi.json)
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import __version__
from .api.routes import router
from .config import get_settings

settings = get_settings()

app = FastAPI(
    title="SPHEREx Blink API",
    version=__version__,
    description="Finds SPHEREx images of a sky position and returns aligned cutouts, stacks and spectra.",
)

# In production the frontend calls /api through a Vercel rewrite (same origin), so CORS only
# matters for local development and direct calls.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
