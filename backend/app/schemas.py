"""Shapes of the API answers. FastAPI publishes them in /openapi.json, and the frontend's types are
generated from there (`npm run gen:api`), so both sides agree by construction.

Units are part of the field names: _deg, _arcmin, _arcsec, _um, _mjysr, _mjy (millijansky), _masyr, mjd.
"""

from typing import Literal

from pydantic import BaseModel, Field


class ErrorBody(BaseModel):
    """The one error shape every failing request answers with."""

    code: str = Field(description="Stable identifier, e.g. no_coverage, upstream_error, busy.")
    message: str = Field(description="Sentence for the person using the page.")
    detail: dict = {}


class ErrorResponse(BaseModel):
    """Envelope of an error answer."""

    error: ErrorBody


class Health(BaseModel):
    """/api/health: what is configured and which features are ready."""

    status: str
    version: str
    collections: list[str]
    jobs: dict[str, int]
    spectrum_ready: bool
    classifier_ready: bool


class Target(BaseModel):
    """/api/resolve: a position SPHEREx can be asked for."""

    name: str | None
    ra_deg: float = Field(description="ICRS, at epoch_mjd (where SPHEREx saw the object).")
    dec_deg: float
    epoch_mjd: float
    pm_ra_masyr: float | None = Field(description="Proper motion in RA, including cos(dec).")
    pm_dec_masyr: float | None
    parallax_mas: float | None
    catalog_ra_deg: float = Field(description="Catalogue position (J2000) or the coordinates as typed.")
    catalog_dec_deg: float
    object_type: str | None
    source: Literal["sesame", "coordinates"]


class CoverageDetector(BaseModel):
    """Images of one detector over a position, with its wavelength range."""

    detector: int
    n_images: int
    lambda_min_um: float
    lambda_max_um: float


class CoveragePass(BaseModel):
    """One survey pass: a burst of images separated from the next by months."""

    pass_index: int
    n_images: int
    mjd_start: float
    mjd_end: float
    date_start_utc: str
    date_end_utc: str
    collections: list[str]


class Coverage(BaseModel):
    """/api/coverage: what SPHEREx has at a position, without reading any image."""

    ra_deg: float
    dec_deg: float
    collections: list[str]
    n_images: int
    detectors: list[CoverageDetector]
    passes: list[CoveragePass]


class GridInfo(BaseModel):
    """The north-up grid every picture of a result is drawn on."""

    ra_deg: float
    dec_deg: float
    fov_arcmin: float
    pixel_scale_arcsec: float
    width_px: int
    height_px: int
    orientation: str


class StretchInfo(BaseModel):
    """The brightness scale shared by every frame and stack of a result."""

    kind: str
    vmin_mjysr: float
    vmax_mjysr: float
    asinh_a: float


class FrameInfo(BaseModel):
    """One image of the series, with what is needed to judge it."""

    index: int
    url: str = Field(description="Frame with flagged pixels hidden (transparent).")
    raw_url: str = Field(description="Same frame with everything the detector recorded.")
    flags_url: str = Field(description="Transparent PNG with the pixels the official recipe excludes.")
    data_url: str = Field(
        description="Aligned values (MJy/sr, background removed), north up, little-endian float16, "
        "grid.width_px x grid.height_px; NaN = no data or a detector defect. Used to add or subtract frames."
    )
    obs_id: str
    collection: str
    detector: int
    pass_index: int
    mjd: float
    date_utc: str
    lambda_um: float = Field(
        description="Wavelength at the field centre in this image (per-pixel spectral calibration map)."
    )
    bandwidth_um: float
    coverage_fraction: float
    background_mjysr: float = Field(description="Level subtracted from this image (zodiacal light).")
    noise_mjysr: float
    flagged_fraction: float
    flag_counts: dict[str, int] = Field(description="Pixels per flag in the piece of image that was read.")
    target_flags: list[str] = Field(description="Flags on the pixel where the target is expected.")
    target_x_frac: float = Field(description="Expected target place: 0 = left edge, 1 = right edge.")
    target_y_frac: float = Field(description="0 = top edge, 1 = bottom edge.")
    quality: str | None = Field(description="L2DQAFLG of the image.")
    astrometry_flag: int | None = Field(description="FINAST: 0 = good astrometry, 1 = partial.")
    contamination: dict[str, bool] = Field(description="*_CONT header keys (airglow, aurora, ...).")
    psf_fwhm_arcsec: float | None
    exposure_s: float | None
    processing_version: str | None
    file_url: str = Field(description="The original L2 FITS file.")


class StackInfo(BaseModel):
    """Images of a survey pass (or of all of them) added together."""

    pass_index: int | None = Field(description="Survey pass; null for the stack of every pass.")
    url: str
    n_images: int
    mjd_start: float
    mjd_end: float
    date_start_utc: str
    date_end_utc: str
    lambda_min_um: float
    lambda_max_um: float
    target_x_frac: float
    target_y_frac: float


class DifferenceInfo(BaseModel):
    """A pass stack minus the reference pass stack (the first pass with 3 or more images)."""

    pass_index: int
    reference_pass_index: int
    url: str
    limit_mjysr: float = Field(description="Black = −limit, white = +limit.")


class SkippedImage(BaseModel):
    """An image left out, and why."""

    obs_id: str
    detector: int
    reason: str


class BlinkResult(BaseModel):
    """Result of an /api/frames job."""

    kind: Literal["blink"]
    key: str
    params: dict
    collections: list[str]
    grid: GridInfo
    stretch: StretchInfo
    detector: int
    n_available: int = Field(description="Images of this detector that cover the position.")
    frames: list[FrameInfo]
    stacks: list[StackInfo]
    stack_all: StackInfo
    differences: list[DifferenceInfo]
    gif_url: str
    skipped: list[SkippedImage]
    notes: list[str]


class SpectrumPoint(BaseModel):
    """The target measured on one image: one wavelength, one date."""

    mjd: float
    date_utc: str
    detector: int
    collection: str
    obs_id: str
    pass_index: int
    lambda_um: float = Field(description="Wavelength of the target's pixel (spectral WCS map).")
    bandwidth_um: float
    flux_mjy: float = Field(description="Millijansky.")
    flux_err_mjy: float = Field(description="Statistical and 3 % calibration error, in quadrature.")
    stat_err_mjy: float = Field(description="Statistical part of the error only.")
    background_mjysr: float
    n_bad_px: int = Field(description="Flagged pixels left out of the aperture.")
    lost_fraction: float = Field(description="Share of the star's light on those pixels (corrected for).")
    flags: list[str] = Field(description="Flag names on the central pixel.")
    lambda_source: Literal["spectral_wcs", "wcs-wave"]
    suspect: bool = Field(
        description="Far from the other points of the same pass at the same wavelength (shown, not removed)."
    )


class SpectrumPass(BaseModel):
    """The points of one survey pass."""

    pass_index: int
    n_points: int
    mjd_start: float
    mjd_end: float


class ClassAlternative(BaseModel):
    """Another class the model considered."""

    label: str
    probability: float | None


class Classification(BaseModel):
    """What the model says the object is. Null when no model is installed."""

    label: str
    probability: float | None
    method: str
    model_version: str | None
    alternatives: list[ClassAlternative]


class SpectrumResult(BaseModel):
    """Result of an /api/spectrum job."""

    kind: Literal["spectrum"]
    key: str
    params: dict
    collections: list[str]
    points: list[SpectrumPoint]
    passes: list[SpectrumPass]
    classification: Classification | None
    skipped: list[SkippedImage]
    notes: list[str]


class LightPoint(BaseModel):
    """The target on one image, divided by itself at the same wavelength in the other images."""

    mjd: float
    residual: float = Field(description="1 = as usual; 1.2 = 20 % brighter than usual at that wavelength.")
    method: Literal["aperture", "wings"] = Field(description="wings = saturated core, PSF wings used.")
    lambda_um: float
    pass_index: int
    detector: int


class ReferencePoint(BaseModel):
    """A comparison star on one image (same kind of residual as the target's)."""

    mjd: float
    residual: float


class VariabilityPass(BaseModel):
    pass_index: int
    n: int
    median: float
    error: float | None
    mjd_start: float
    mjd_end: float


class BandCell(BaseModel):
    median: float
    n: int


class BandRow(BaseModel):
    """Median residual of one wavelength band in each survey pass (keys: pass index)."""

    lambda_min_um: float
    lambda_max_um: float
    passes: dict[str, BandCell]


class PeriodInfo(BaseModel):
    period_d: float
    power: float = Field(description="Lomb–Scargle power, 0 to 1.")
    span_d: float
    largest_gap_d: float
    supported: bool = Field(description="False when the sampling cannot support this period.")
    reference_power: float | None = None


class Verdict(BaseModel):
    variable: bool | None
    threshold: float = Field(description="Scatter above which the target is called variable.")
    text: str


class VariabilityResult(BaseModel):
    """Result of an /api/variability job."""

    kind: Literal["variability"]
    key: str
    params: dict
    collections: list[str]
    n_images: int
    n_available: int
    light_curve: list[LightPoint]
    reference: list[ReferencePoint]
    n_comparison_stars: int
    target_scatter: float | None
    reference_scatter: float | None
    wing_share: float = Field(description="Share of target points measured on the PSF wings.")
    passes: list[VariabilityPass]
    bands: list[BandRow]
    period: PeriodInfo | None
    verdict: Verdict
    method: dict
    skipped: list[SkippedImage]
    notes: list[str]


class JobStatus(BaseModel):
    """A long request: poll /api/jobs/{job_id} until status is done or failed."""

    job_id: str
    kind: str
    status: Literal["queued", "running", "done", "failed"]
    progress: float = Field(description="0 to 1.")
    stage: str = Field(description="What is happening now, for the progress bar.")
    result: BlinkResult | SpectrumResult | VariabilityResult | None = Field(None, discriminator="kind")
    error: ErrorBody | None = None


class OverlaySource(BaseModel):
    """A catalogue source placed on the frame (x, y as fractions from the top-left)."""

    id: str
    ra_deg: float = Field(description="At the date asked for, when the catalogue gives proper motion.")
    dec_deg: float
    mag: float | None
    band: str
    x_frac: float
    y_frac: float


class Overlay(BaseModel):
    """/api/overlay: sources of another mission inside the field."""

    catalog: Literal["gaia", "wise"]
    label: str
    epoch_note: str
    sources: list[OverlaySource]
