"""API contract. Endpoints not built yet answer 501 so the frontend can be typed against the schema now.

Order of construction follows the hackathon plan: health → resolve → coverage → frames → difference
→ spectrum → jobs.
"""

from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from .. import __version__
from ..config import get_settings

router = APIRouter()


def _not_yet(step: str) -> HTTPException:
    return HTTPException(status_code=501, detail=f"Not implemented yet ({step}).")


@router.get("/health")
def health() -> dict:
    """Liveness check used by Render and by the frontend."""
    s = get_settings()
    return {"status": "ok", "version": __version__, "collections": s.sia_collections}


@router.get("/resolve")
def resolve(
    name: str | None = Query(None, description="Object name, resolved with Sesame (CDS)."),
    ra: str | None = Query(None, description="Decimal degrees or sexagesimal, e.g. 08h55m10.831s"),
    dec: str | None = Query(None, description="Decimal degrees or sexagesimal, e.g. -7d14m42.53s"),
):
    """Coordinates in decimal degrees; for named stars also proper motion and the position today."""
    raise _not_yet("step 0")


@router.get("/coverage")
def coverage(
    ra_deg: float = Query(..., ge=0, lt=360),
    dec_deg: float = Query(..., ge=-90, le=90),
    fov_arcmin: float = Query(6.0, gt=0),
):
    """Every SPHEREx image covering the position (DR1 + QR3), without downloading any:
    date, detector, survey pass, approximate channel and wavelength. Feeds the coverage map."""
    raise _not_yet("step 1")


@router.get("/frames")
def frames(
    ra_deg: float = Query(..., ge=0, lt=360),
    dec_deg: float = Query(..., ge=-90, le=90),
    fov_arcmin: float = Query(6.0, gt=0),
    detector: int = Query(..., ge=1, le=6),
    view: Literal["channel", "pass", "all"] = "channel",
):
    """Aligned, north-up cutouts (float32, MJy/sr) for the blink viewer, with per-frame metadata."""
    raise _not_yet("steps 2-3")


@router.get("/difference")
def difference(
    ra_deg: float = Query(..., ge=0, lt=360),
    dec_deg: float = Query(..., ge=-90, le=90),
    fov_arcmin: float = Query(6.0, gt=0),
    detector: int = Query(..., ge=1, le=6),
    pass_index: int = Query(1, ge=1, description="Pass to compare against the first one."),
):
    """Stacked pass N minus stacked pass 1, using only channels present in both."""
    raise _not_yet("step 3")


@router.get("/spectrum")
def spectrum(
    ra_deg: float = Query(..., ge=0, lt=360),
    dec_deg: float = Query(..., ge=-90, le=90),
    mode: Literal["cube", "pass"] = "cube",
):
    """Quick-look spectrum from the DR1 all-sky cube, or one spectrum per survey pass from L2 images."""
    raise _not_yet("step 6")


@router.get("/jobs/{job_id}")
def job_status(job_id: str):
    """Status of a long-running request (per-pass spectra, large fields)."""
    raise _not_yet("extra")
