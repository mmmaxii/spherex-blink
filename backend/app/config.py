"""Every service URL, data release and limit lives here, so a new SPHEREx release is a one-file change.

Values verified on 2026-11-13/14 against IRSA (see CLAUDE.md). Override any of them with an
environment variable of the same name prefixed by SPHEREX_ (e.g. SPHEREX_ALLOWED_ORIGINS).
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPHEREX_", env_file=".env", extra="ignore")

    # --- Data releases -------------------------------------------------------------------------
    # DR1 (year 1) + QR3 (year 2, weekly) share the R7 pipeline and must be queried together.
    # QR2 is no longer searchable and must not be mixed with them.
    # A new release = add its collection name here (or set SPHEREX_SIA_COLLECTIONS on Render).
    sia_collections: list[str] = ["spherex_dr1", "spherex_qr3"]
    sia_deep_collections: list[str] = ["spherex_dr1_deep", "spherex_qr3_deep"]
    sia_cube_collection: str = "spherex_dr1_cube"

    # --- Services ------------------------------------------------------------------------------
    sia_url: str = "https://irsa.ipac.caltech.edu/SIA"
    most_url: str = "https://irsa.ipac.caltech.edu/cgi-bin/MOST/nph-most"
    s3_https_base: str = "https://nasa-irsa-spherex.s3.amazonaws.com/"  # bucket region: us-east-1
    sesame_url: str = "https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp/S?"  # may redirect to a mirror
    gaia_tap_url: str = "https://gea.esac.esa.int/tap-server/tap/sync"
    irsa_scs_url: str = "https://irsa.ipac.caltech.edu/SCS"
    http_timeout_s: float = 60.0
    http_tries: int = 4  # attempts per request to an external service
    http_backoff_s: float = 1.5  # wait before retry n is backoff * 2**(n-1), plus jitter
    http_backoff_max_s: float = 4.0  # ...but never longer than this between two attempts
    # IRSA's image search answered 502 to 11 of 12 requests on 15 Nov 2026 (each in ~0.7 s): more
    # attempts, with the capped wait, give a busy archive a real chance without a long wait.
    sia_tries: int = 8

    # --- Limits (protect IRSA and our single instance) -----------------------------------------
    max_parallel_irsa: int = 8  # IRSA tutorials recommend <= 10 parallel requests
    max_parallel_s3: int = 12  # images read at the same time inside one job
    max_concurrent_jobs: int = 2  # CPU-heavy work (reprojection, stacking) at the same time
    max_queued_jobs: int = 12  # beyond this the API answers 503 "busy"
    job_ttl_s: float = 3600.0  # finished jobs are forgotten after this (their products stay on disk)
    max_fov_arcmin: float = 20.0
    default_max_frames: int = 24
    max_frames_limit: int = 80
    min_frames: int = 2  # a blink needs at least two usable images
    max_overlay_sources: int = 150

    # --- Reading L2 files from S3 --------------------------------------------------------------
    # fsspec read-ahead. One image takes ~15 range requests (headers of every extension, the rows,
    # the compressed flags, the wavelength table). Measured from Chile for 13 images in parallel:
    # 256 KB → 23 s, 1 MB → 41 s (bandwidth-bound). Next to the bucket (Render) latency is ~20 ms.
    s3_block_size_bytes: int = 262_144
    frame_tries: int = 2  # attempts per image before it is skipped
    sia_radius_deg: float = 0.01  # images whose footprint contains the position
    max_astrometry_flag: int = 1  # FINAST: 0 good, 1 partial; images above this are skipped

    # --- Instrument (Explanatory Supplement v2.1; verified in DR1 headers) ---------------------
    pixel_scale_arcsec: float = 6.15
    detector_size_px: int = 2040
    pass_gap_days: float = 30.0  # gaps longer than this separate survey passes
    reference_mjd: float = 61050.0  # ~Jan 2026, middle of DR1 + QR3; positions "today" use this epoch

    # --- Imaging -------------------------------------------------------------------------------
    output_oversample: int = 2  # output grid pixel = 6.15" / this (the PSF is undersampled)
    reproject_method: Literal["interp", "exact"] = "interp"  # "exact" conserves flux, slower
    min_coverage_fraction: float = 0.3  # images covering less of the field are skipped
    stack_sigma_clip: float = 3.0
    mask_grow_px: int = 1  # flagged pixels are hidden together with this many neighbours
    gif_frame_ms: int = 600

    # --- Spectra and classification ------------------------------------------------------------
    model_dir: str = "models"  # trained classifier files (joblib), not in git
    classifier_file: str = "classifier.joblib"
    spectrum_max_images: int = 150  # images read for one spectrum (all detectors)
    spectrum_cutout_half_px: int = 12  # cutout of 25 x 25 pixels around the target

    # Per-pixel calibration maps (public S3 bucket, one file per detector, {d} = 1..6). The
    # Explanatory Supplement (v2.1, §4.3.1) asks for CWAVE/CBAND in science work, not WCS-WAVE.
    # Downloaded once into cache_dir/calibration (~50 MB per detector) and memory-mapped.
    spectral_wcs_key: str = (
        "dr1/spectral_wcs/cal-swcs-v5-2026-191/{d}/spectral_wcs_D{d}_spx_cal-swcs-v5-2026-191.fits"
    )
    solid_angle_key: str = (
        "dr1/solid_angle_pixel_map/cal-sapm-v3-2026-191/{d}/"
        "solid_angle_pixel_map_D{d}_spx_cal-sapm-v3-2026-191.fits"
    )

    # Aperture photometry, validated on eps Ind B in validation/notebooks/maxi/03 and 04 (15 Nov 2026).
    aperture_radius_px: float = 2.5  # encloses 97.7-98.8 % of the ePSF on all six detectors
    background_inner_px: float = 6.0  # sky annulus; stars inside it are removed by sigma clipping
    background_outer_px: float = 10.0
    psf_sigma_px: float = 0.75  # Gaussian stand-in for the ePSF, used to weigh flagged pixels
    max_lost_light: float = 0.20  # skip the image if more of the star's light falls on flagged pixels
    calibration_systematic: float = 0.03  # added in quadrature, as the official IRSA photometry does
    suspect_factor: float = 2.0  # a point this far from its same-pass neighbours is marked suspect

    # --- Web -----------------------------------------------------------------------------------
    allowed_origins: list[str] = ["http://localhost:5173", "https://spherex-blink.vercel.app"]
    cache_dir: str = ".cache"
    sia_cache_ttl_s: float = 6 * 3600.0  # QR3 grows weekly; a few hours is fresh enough
    resolve_cache_ttl_s: float = 7 * 86400.0
    overlay_cache_ttl_s: float = 7 * 86400.0
    max_products: int = 400  # product folders kept on disk (oldest removed first)
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
