"""The API. Routes only validate the request and call data/ or pipeline/; no science here.

Quick requests answer directly (resolve, coverage, overlay). Long ones (frames, spectrum) answer
at once with a job: the page polls /api/jobs/{job_id} until `status` is "done" or "failed".
Everything is a GET with its parameters in the URL, so any view can be linked or embedded.
"""

from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from .. import __version__, schemas
from ..config import get_settings
from ..core.jobs import get_job_manager
from ..core.products import get_product_store
from ..data import catalogs, resolve, sia
from ..errors import BadRequest, NoCoverage, NotFound
from ..imaging.grid import make_grid, to_fraction
from ..pipeline import blink
from ..pipeline import spectrum as spectrum_pipeline
from ..pipeline.common import mjd_to_iso
from ..spectra import classifier

router = APIRouter()

ERRORS = {code: {"model": schemas.ErrorResponse} for code in (400, 404, 422, 501, 502, 503, 504)}

RaDeg = Query(..., ge=0, lt=360, description="Right ascension, ICRS, decimal degrees.")
DecDeg = Query(..., ge=-90, le=90, description="Declination, ICRS, decimal degrees.")
PmRa = Query(0.0, description="Proper motion in RA including cos(dec) [mas/yr], from /resolve.")
PmDec = Query(0.0, description="Proper motion in Dec [mas/yr], from /resolve.")
EpochMjd = Query(None, description="Date (MJD) of ra_deg/dec_deg when proper motion is given.")


def _check_fov(fov_arcmin: float) -> None:
    limit = get_settings().max_fov_arcmin
    if fov_arcmin > limit:
        raise BadRequest(
            f"The field of view can be at most {limit:g} arcmin.", detail={"max_fov_arcmin": limit}
        )


@router.get("/health", response_model=schemas.Health)
def health():
    """Liveness check used by Render and by the frontend."""
    s = get_settings()
    return {
        "status": "ok",
        "version": __version__,
        "collections": s.sia_collections,
        "jobs": get_job_manager().stats(),
        "spectrum_ready": spectrum_pipeline.is_ready(),
        "classifier_ready": classifier.is_ready(),
    }


@router.get("/resolve", response_model=schemas.Target, responses=ERRORS)
def resolve_target(
    name: str | None = Query(None, description="Object name, resolved with Sesame (CDS)."),
    ra: str | None = Query(None, description="Decimal degrees or sexagesimal, e.g. 08h55m10.831s"),
    dec: str | None = Query(None, description="Decimal degrees or sexagesimal, e.g. -7d14m42.53s"),
):
    """A name or typed coordinates → decimal degrees. For named objects with proper motion the
    position is the one at the SPHEREx epoch, not J2000 (Barnard's Star has moved 4.5')."""
    if name:
        return resolve.from_name(name).to_dict()
    if ra and dec:
        return resolve.from_coordinates(ra, dec).to_dict()
    raise BadRequest("Give an object name, or both ra and dec.")


@router.get("/coverage", response_model=schemas.Coverage, responses=ERRORS)
def coverage(ra_deg: float = RaDeg, dec_deg: float = DecDeg):
    """Every SPHEREx image covering the position, without reading any: how many per detector and
    per survey pass. Feeds the detector picker."""
    images = sia.search(ra_deg, dec_deg)
    if not images:
        raise NoCoverage("SPHEREx has no public images of this position yet.")
    summary = sia.summarize(images)
    for p in summary["passes"]:
        p["date_start_utc"], p["date_end_utc"] = mjd_to_iso(p["mjd_start"]), mjd_to_iso(p["mjd_end"])
    return {"ra_deg": ra_deg, "dec_deg": dec_deg, "collections": get_settings().sia_collections, **summary}


@router.get("/frames", response_model=schemas.JobStatus, responses=ERRORS)
def frames(
    ra_deg: float = RaDeg,
    dec_deg: float = DecDeg,
    fov_arcmin: float = Query(6.0, gt=0.5, description="Side of the field."),
    detector: int = Query(..., ge=1, le=6, description="SPHEREx detector (1–6 = six wavelength ranges)."),
    max_frames: int | None = Query(None, ge=2, description="Images to read, spread over the survey passes."),
    pm_ra_masyr: float = PmRa,
    pm_dec_masyr: float = PmDec,
    epoch_mjd: float | None = EpochMjd,
):
    """Starts (or joins) the blink job: aligned north-up frames, one stack per survey pass,
    differences between passes and a GIF. The result arrives in `result` when `status` is "done"."""
    s = get_settings()
    _check_fov(fov_arcmin)
    params = blink.BlinkParams(
        ra_deg=round(ra_deg, 6),
        dec_deg=round(dec_deg, 6),
        fov_arcmin=fov_arcmin,
        detector=detector,
        max_frames=min(max_frames or s.default_max_frames, s.max_frames_limit),
        pm_ra_masyr=pm_ra_masyr,
        pm_dec_masyr=pm_dec_masyr,
        epoch_mjd=epoch_mjd,
    )
    return blink.start(params).to_dict()


@router.get("/spectrum", response_model=schemas.JobStatus, responses=ERRORS)
def spectrum(
    ra_deg: float = RaDeg,
    dec_deg: float = DecDeg,
    mode: Literal["pass", "cube"] = Query(
        "pass", description="pass: one spectrum per survey pass, from the images."
    ),
    pm_ra_masyr: float = PmRa,
    pm_dec_masyr: float = PmDec,
    epoch_mjd: float | None = EpochMjd,
):
    """Starts (or joins) the spectrum job. Answers 501 until the photometry is validated."""
    params = spectrum_pipeline.SpectrumParams(
        ra_deg=round(ra_deg, 6),
        dec_deg=round(dec_deg, 6),
        mode=mode,
        pm_ra_masyr=pm_ra_masyr,
        pm_dec_masyr=pm_dec_masyr,
        epoch_mjd=epoch_mjd,
    )
    return spectrum_pipeline.start(params).to_dict()


@router.get("/jobs/{job_id}", response_model=schemas.JobStatus, responses=ERRORS)
def job_status(job_id: str):
    """Progress of a job and, when done, its result."""
    job = get_job_manager().get(job_id)
    if job is None:
        raise NotFound("This job is no longer known. Run the search again.")
    return job.to_dict()


@router.get("/overlay", response_model=schemas.Overlay, responses=ERRORS)
def overlay(
    ra_deg: float = RaDeg,
    dec_deg: float = DecDeg,
    fov_arcmin: float = Query(6.0, gt=0.5),
    catalog: Literal["gaia", "wise"] = "gaia",
    mjd: float | None = Query(None, description="Date to move Gaia sources to (default: SPHEREx epoch)."),
):
    """Sources of another mission inside the field, already placed on the frame (x_frac, y_frac)."""
    s = get_settings()
    _check_fov(fov_arcmin)
    grid = make_grid(ra_deg, dec_deg, fov_arcmin)
    radius_deg = fov_arcmin / 60 / 2 * 1.42  # the circle that contains the square field
    mjd = mjd if mjd is not None else s.reference_mjd
    sources = []
    for source in catalogs.cone(catalog, round(ra_deg, 5), round(dec_deg, 5), round(radius_deg, 4)):
        ra, dec = source["ra_deg"], source["dec_deg"]
        if source["pm_ra_masyr"] is not None and source["pm_dec_masyr"] is not None:
            epoch_mjd = resolve.MJD_J2000 + (source["epoch_jyear"] - 2000.0) * resolve.DAYS_PER_YEAR
            ra, dec = resolve.propagate(
                ra, dec, source["pm_ra_masyr"], source["pm_dec_masyr"], epoch_mjd, mjd
            )
        x_frac, y_frac = (float(v) for v in to_fraction(grid, ra, dec))
        if 0 <= x_frac <= 1 and 0 <= y_frac <= 1:
            sources.append(
                {
                    "id": source["id"],
                    "ra_deg": ra,
                    "dec_deg": dec,
                    "mag": source["mag"],
                    "band": source["band"],
                    "x_frac": round(x_frac, 5),
                    "y_frac": round(y_frac, 5),
                }
            )
    if catalog == "gaia":
        label, note = "Gaia DR3", f"Positions moved to {mjd_to_iso(mjd)[:10]} with Gaia proper motions."
    else:
        label, note = "AllWISE", "Positions as observed by WISE around 2010; fast objects will be offset."
    return {"catalog": catalog, "label": label, "epoch_note": note, "sources": sources}


@router.get("/products/{kind}/{key}/{name}", responses=ERRORS, include_in_schema=False)
def product(kind: str, key: str, name: str):
    """Files written by a pipeline (PNG frames, GIF). The key changes when the content does."""
    path = get_product_store().file(kind, key, name)
    return FileResponse(path, headers={"Cache-Control": "public, max-age=604800, immutable"})
