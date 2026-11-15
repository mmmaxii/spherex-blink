"""Per-pixel calibration maps of the six detectors: wavelength, bandwidth and pixel solid angle.

The wavelength inside each L2 file (WCS-WAVE) is a 9 x 9 lookup table, fine for labels. For science
the Explanatory Supplement (v2.1, §4.3.1) asks for the spectral WCS files (CWAVE = wavelength where
the pixel's cumulative transmission reaches 50 %, CBAND = CWAVE / R). The official photometry also
converts MJy/sr to flux with each pixel's own solid angle (§3.3, step 8), not the median.

Measured on 15 Nov 2026 (validation/notebooks/maxi/03): WCS-WAVE differs from CWAVE by at most
0.13 % (a channel is ~2.5 % wide); the pixel solid angle varies by about ±1.3 % around OMEGA_MEDIAN.

The maps are the same for every image of a release, so each detector's two files (~50 MB) are
downloaded once into cache_dir/calibration and memory-mapped: a lookup costs no network.
"""

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy.io import fits

from ..config import get_settings
from ..core.http import fetch

log = logging.getLogger(__name__)

_LOCK = threading.Lock()  # one download per file, even when many images are measured in parallel
_MAPS: dict[int, "DetectorMaps"] = {}


@dataclass(frozen=True)
class DetectorMaps:
    lambda_um: np.ndarray  # CWAVE, 2040 x 2040, memory-mapped
    bandwidth_um: np.ndarray  # CBAND
    solid_angle_arcsec2: np.ndarray


@dataclass(frozen=True)
class PixelCalibration:
    lambda_um: float
    bandwidth_um: float
    solid_angle_arcsec2: float


def _local_copy(key: str) -> Path:
    """The file on disk, downloaded from the bucket the first time (written atomically)."""
    folder = Path(get_settings().cache_dir) / "calibration"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / Path(key).name
    if not path.exists():
        log.info("downloading calibration file %s", key)
        part = path.with_suffix(".part")
        part.write_bytes(fetch("s3-calibration", get_settings().s3_https_base + key).content)
        part.replace(path)
    return path


def detector_maps(detector: int) -> DetectorMaps:
    """Maps of one detector (1-6), downloaded on first use."""
    with _LOCK:
        if detector not in _MAPS:
            s = get_settings()
            swcs = fits.open(_local_copy(s.spectral_wcs_key.format(d=detector)), memmap=True)
            sapm = fits.open(_local_copy(s.solid_angle_key.format(d=detector)), memmap=True)
            _MAPS[detector] = DetectorMaps(
                lambda_um=swcs["CWAVE"].data,
                bandwidth_um=swcs["CBAND"].data,
                solid_angle_arcsec2=sapm["IMAGE"].data,
            )
        return _MAPS[detector]


def at(detector: int, x_px: float, y_px: float) -> PixelCalibration:
    """Values of the pixel that contains detector position (x_px, y_px), 0-based, full detector."""
    maps = detector_maps(detector)
    n_rows, n_cols = maps.lambda_um.shape
    row = min(max(int(round(y_px)), 0), n_rows - 1)
    col = min(max(int(round(x_px)), 0), n_cols - 1)
    return PixelCalibration(
        lambda_um=float(maps.lambda_um[row, col]),
        bandwidth_um=float(maps.bandwidth_um[row, col]),
        solid_angle_arcsec2=float(maps.solid_angle_arcsec2[row, col]),
    )
