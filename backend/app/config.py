"""Every service URL, data release and limit lives here, so a new SPHEREx release is a one-file change.

Values verified on 2026-11-13 against IRSA (see docs/data-notes.md). Override any of them with an
environment variable of the same name prefixed by SPHEREX_ (e.g. SPHEREX_ALLOWED_ORIGINS).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SPHEREX_", env_file=".env", extra="ignore")

    # --- Data releases -------------------------------------------------------------------------
    # DR1 (year 1) + QR3 (year 2, weekly) share the R7 pipeline and must be queried together.
    # QR2 is no longer searchable and must not be mixed with them.
    sia_collections: list[str] = ["spherex_dr1", "spherex_qr3"]
    sia_deep_collections: list[str] = ["spherex_dr1_deep", "spherex_qr3_deep"]
    sia_cube_collection: str = "spherex_dr1_cube"

    # --- Services ------------------------------------------------------------------------------
    sia_url: str = "https://irsa.ipac.caltech.edu/SIA"
    most_url: str = "https://irsa.ipac.caltech.edu/cgi-bin/MOST/nph-most"
    s3_https_base: str = "https://nasa-irsa-spherex.s3.amazonaws.com/"  # bucket region: us-east-1
    sesame_url: str = "https://cds.unistra.fr/cgi-bin/nph-sesame/-oxp/S?"
    http_timeout_s: float = 120.0

    # --- Limits (protect IRSA and our single instance) -----------------------------------------
    max_parallel_irsa: int = 8  # IRSA tutorials recommend <= 10 parallel requests
    max_parallel_s3: int = 16
    max_concurrent_jobs: int = 2  # CPU-heavy work (reprojection, stacking) at the same time
    max_fov_arcmin: float = 20.0

    # --- Instrument (Explanatory Supplement v2.1; verified in DR1 headers) ---------------------
    pixel_scale_arcsec: float = 6.15
    detector_size_px: int = 2040
    pass_gap_days: float = 30.0  # gaps longer than this separate survey passes

    # --- Web -----------------------------------------------------------------------------------
    allowed_origins: list[str] = ["http://localhost:5173", "https://spherex-blink.vercel.app"]
    cache_dir: str = ".cache"


@lru_cache
def get_settings() -> Settings:
    return Settings()
