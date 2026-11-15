"""Shared test setup. Tests run without internet: external services are replaced by saved answers
(tests/fixtures) or synthetic images. Tests that do use the network are marked `live` and only run
with `pytest -m live`.
"""

import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

# Must be set before the app is imported: settings are read once.
os.environ["SPHEREX_CACHE_DIR"] = tempfile.mkdtemp(prefix="spherex-blink-tests-")
os.environ["SPHEREX_HTTP_BACKOFF_S"] = "0"

from astropy.wcs import WCS  # noqa: E402

from app.data.l2 import Cutout  # noqa: E402
from app.data.sia import ImageRef  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"

FLAG_BITS = {0: "TRANSIENT", 1: "OVERFLOW", 2: "SUR_ERROR", 10: "HOT", 21: "SOURCE"}


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


def make_ref(index: int, detector: int = 4, mjd: float = 60800.0, pass_index: int = 0) -> ImageRef:
    return ImageRef(
        obs_id=f"TEST_{index:04d}",
        collection="spherex_dr1",
        detector=detector,
        mjd=mjd,
        s3_key=f"dr1/level2/test/{index}.fits",
        access_url=f"https://example.org/{index}.fits",
        lambda_min_um=2.4,
        lambda_max_um=3.8,
        pass_index=pass_index,
    )


def make_cutout(
    ref: ImageRef,
    ra_deg: float,
    dec_deg: float,
    *,
    size_px: int = 61,
    rotation_deg: float = 30.0,
    star_offset_px: tuple[float, float] = (0.0, 0.0),
    hot_pixel: bool = True,
    seed: int = 0,
) -> Cutout:
    """Synthetic L2 cutout: rotated TAN WCS (6.15"/px), flat sky + noise, one star at the position
    (plus an optional offset) and one flagged hot pixel (6 px from the centre)."""
    rng = np.random.default_rng(seed)
    centre = (size_px - 1) / 2
    scale_deg = 6.15 / 3600
    angle = np.radians(rotation_deg)
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.crval = [ra_deg, dec_deg]
    wcs.wcs.crpix = [centre + 1, centre + 1]
    wcs.wcs.cd = scale_deg * np.array([[-np.cos(angle), np.sin(angle)], [np.sin(angle), np.cos(angle)]])

    yy, xx = np.mgrid[:size_px, :size_px]
    star_x, star_y = centre + star_offset_px[0], centre + star_offset_px[1]
    image = 0.5 + rng.normal(0, 0.02, (size_px, size_px))  # zodiacal level + noise [MJy/sr]
    image += 5.0 * np.exp(-((xx - star_x) ** 2 + (yy - star_y) ** 2) / (2 * 0.7**2))
    flags = np.zeros((size_px, size_px), dtype=np.int32)
    flags[int(round(star_y)), int(round(star_x))] |= 1 << 21  # SOURCE (kept by the recipe)
    if hot_pixel:
        image[24, 34] = 80.0
        flags[24, 34] |= 1 << 10  # HOT (excluded by the recipe)
    return Cutout(
        ref=ref,
        image_mjysr=image.astype(np.float32),
        wcs=wcs,
        x_px=centre,
        y_px=centre,
        detector_x_px=1000.0,
        detector_y_px=1000.0,
        mjd=ref.mjd,
        lambda_um=2.5 + 0.01 * (seed % 7),
        bandwidth_um=0.07,
        flags=flags,
        flag_bits=dict(FLAG_BITS),
        variance=np.full((size_px, size_px), 0.02**2, dtype=np.float32),
        psf_fwhm_arcsec=8.7,
        dqa="Pass",
        astrometry_flag=0,
        contamination={"AURORA_CONT": False},
        exposure_s=113.58,
        pipeline_version="7.0.5",
    )
