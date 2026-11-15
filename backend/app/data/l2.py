"""Reading a small piece of an L2 image straight from S3, without downloading the 65 MB file.

astropy + fsspec fetch only the headers and the rows that are needed (HTTP Range), about 1–2 MB
per image. Ported from 01_exploratory.ipynb (cells 4–8) and from the blink notebook (cell 4).

Rules that this module keeps:
- what the file says wins: image size, flag names and the wavelength table are read from it;
- every pixel has its own wavelength (WCS key "W", with SIP removed), so the cutout carries the
  wavelength at the requested position. That WCS is a 9 x 9 lookup table: good for labels and
  plots, approximate for science (the spectral calibration products are the precise source);
- images whose astrometry failed (FINAST >= 2) are not used.

File layout (DR1): PRIMARY (VERSION), IMAGE [MJy/sr], FLAGS (compressed), VARIANCE, ZODI (not
subtracted from IMAGE), EPSF (441 zones; 451 in D3), WCS-WAVE.
"""

import logging
import threading
import warnings
from dataclasses import dataclass, field

import aiohttp
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS, FITSFixedWarning

from ..config import get_settings
from . import flags as flaglib
from .sia import ImageRef

log = logging.getLogger(__name__)

# SPHEREx headers trigger harmless "fixed" notices in astropy; set once here because
# warnings.catch_warnings() is not safe across the threads that read images in parallel.
warnings.filterwarnings("ignore", category=FITSFixedWarning)

# wcslib parses headers with global state; building WCS objects one at a time keeps threads safe.
_WCS_LOCK = threading.Lock()


class FrameSkipped(Exception):
    """This image cannot be used for this position; the reason is shown to the user."""


@dataclass
class Cutout:
    ref: ImageRef
    image_mjysr: np.ndarray  # float32 [MJy/sr], detector orientation, zodiacal light included
    wcs: WCS  # celestial WCS of the cutout (TAN-SIP)
    x_px: float  # position asked for, in cutout pixels (0-based)
    y_px: float
    detector_x_px: float  # same position in the full detector
    detector_y_px: float
    mjd: float
    lambda_um: float  # at the position
    bandwidth_um: float
    flags: np.ndarray | None = None
    flag_bits: dict[int, str] = field(default_factory=dict)
    variance: np.ndarray | None = None  # [(MJy/sr)^2]
    zodi_mjysr: np.ndarray | None = None
    psf_fwhm_arcsec: float | None = None
    dqa: str | None = None  # L2DQAFLG
    astrometry_flag: int | None = None  # FINAST: 0 good, 1 partial (corners off by ~2 px), >= 2 unusable
    pixel_solid_angle_arcsec2: float | None = None  # OMEGA_MEDIAN (VERIFY the key in a real header)
    contamination: dict[str, bool] = field(default_factory=dict)  # *_CONT header keys
    exposure_s: float | None = None
    pipeline_version: str | None = None


def s3_url(ref: ImageRef) -> str:
    return get_settings().s3_https_base + ref.s3_key


def read_cutout(
    ref: ImageRef,
    ra_deg: float,
    dec_deg: float,
    half_size_px: int,
    *,
    with_flags: bool = True,
    with_variance: bool = False,
    with_zodi: bool = False,
) -> Cutout:
    """Square piece of one image around a sky position (clipped at the detector edges)."""
    s = get_settings()
    fsspec_kwargs = {
        "block_size": s.s3_block_size_bytes,
        "cache_type": "bytes",
        "client_kwargs": {"timeout": aiohttp.ClientTimeout(total=s.http_timeout_s)},
    }
    with fits.open(s3_url(ref), use_fsspec=True, lazy_load_hdus=True, fsspec_kwargs=fsspec_kwargs) as hdul:
        image_hdu = hdul["IMAGE"]
        header = image_hdu.header
        n_rows, n_cols = int(header["NAXIS2"]), int(header["NAXIS1"])
        finast = header.get("FINAST")
        if isinstance(finast, int) and finast > s.max_astrometry_flag:
            raise FrameSkipped(f"astrometry not reliable (FINAST = {finast})")
        with _WCS_LOCK:
            wcs = WCS(header)
            x, y = (float(v) for v in wcs.world_to_pixel_values(ra_deg, dec_deg))
        if not (np.isfinite(x) and np.isfinite(y) and 0 <= x < n_cols and 0 <= y < n_rows):
            raise FrameSkipped("position outside the detector")

        r0, r1 = max(0, round(y) - half_size_px), min(n_rows, round(y) + half_size_px + 1)
        c0, c1 = max(0, round(x) - half_size_px), min(n_cols, round(x) + half_size_px + 1)
        window = (slice(r0, r1), slice(c0, c1))

        cutout = Cutout(
            ref=ref,
            image_mjysr=np.asarray(image_hdu.section[window], dtype=np.float32),
            wcs=wcs[window],
            x_px=x - c0,
            y_px=y - r0,
            detector_x_px=x,
            detector_y_px=y,
            mjd=float(header.get("MJD-AVG", ref.mjd)),
            lambda_um=float("nan"),
            bandwidth_um=float("nan"),
            psf_fwhm_arcsec=_optional_float(header.get("PSF_FWHM")),
            dqa=str(header["L2DQAFLG"]) if "L2DQAFLG" in header else None,
            astrometry_flag=finast if isinstance(finast, int) else None,
            pixel_solid_angle_arcsec2=_optional_float(header.get("OMEGA_MEDIAN")),
            contamination={k: bool(v) for k, v in header.items() if k.endswith("_CONT")},
            exposure_s=_optional_float(header.get("XPOSURE")),
            pipeline_version=str(hdul[0].header.get("VERSION", "")) or None,
        )
        if with_flags:
            flags_hdu = hdul["FLAGS"]  # RICE-compressed; astropy reads only the tiles needed
            cutout.flags = np.asarray(flags_hdu.section[window])
            cutout.flag_bits = flaglib.bit_names(flags_hdu.header)
        if with_variance:
            cutout.variance = np.asarray(hdul["VARIANCE"].section[window], dtype=np.float32)
        if with_zodi:
            cutout.zodi_mjysr = np.asarray(hdul["ZODI"].section[window], dtype=np.float32)

        # Wavelength of the position: alternate WCS "W" (lookup table in the WCS-WAVE extension).
        # The SIP distortion belongs to the sky WCS only and must be removed here.
        with _WCS_LOCK:
            wave = WCS(header, fobj=hdul, key="W")
            wave.sip = None
            lambda_um, bandwidth_um = wave.pixel_to_world_values(x, y)
        cutout.lambda_um, cutout.bandwidth_um = float(lambda_um), float(bandwidth_um)
    return cutout


def _optional_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
