"""Per-pixel calibration of the six detectors: wavelength, bandwidth and pixel solid angle.

The wavelength inside each L2 file (WCS-WAVE) is a 9 x 9 lookup table, fine for labels. For science
the Explanatory Supplement (v2.1, §4.3.1) asks for the spectral WCS files (CWAVE = wavelength where
the pixel's cumulative transmission reaches 50 %, CBAND = CWAVE / R). The official photometry also
converts MJy/sr to flux with each pixel's own solid angle (§3.3, step 8), not the median.

Measured on 15 Nov 2026 (validation/notebooks/maxi/03): WCS-WAVE differs from CWAVE by at most
0.13 % (a channel is ~2.5 % wide); the pixel solid angle varies by about ±1.3 % around OMEGA_MEDIAN.

The official maps weigh 300 MB for the six detectors; downloading them on the server filled most of
the instance's memory. The API ships a grid of every 8th pixel of those maps instead
(calibration_dr1.npz, ~5 MB, built by scripts/build_calibration_grid.py) and interpolates it
bilinearly. Against the full maps: wavelength within 0.04 % for 99 % of the pixels, bandwidth within
5 % (it has ~0.5 % pixel-to-pixel noise; it only sets the "same wavelength" window), solid angle
within 2e-7 (fluxes do not change).
"""

import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

GRID_FILE = Path(__file__).with_name("calibration_dr1.npz")

_LOCK = threading.Lock()  # the grid is read once, even when many images are measured in parallel
_GRID: "CalibrationGrid | None" = None


@dataclass(frozen=True)
class CalibrationGrid:
    knots_px: np.ndarray  # detector pixel index of each grid line (same for rows and columns)
    lambda_um: np.ndarray  # CWAVE at the knots, shape (6 detectors, knots, knots)
    bandwidth_um: np.ndarray  # CBAND
    solid_angle_arcsec2: np.ndarray


@dataclass(frozen=True)
class PixelCalibration:
    lambda_um: float
    bandwidth_um: float
    solid_angle_arcsec2: float


def grid() -> CalibrationGrid:
    """The grid of the six detectors, read from the package on first use."""
    global _GRID
    with _LOCK:
        if _GRID is None:
            with np.load(GRID_FILE) as data:
                _GRID = CalibrationGrid(
                    knots_px=data["knots_px"].astype(np.int64),
                    lambda_um=data["lambda_um"],
                    bandwidth_um=data["bandwidth_um"],
                    solid_angle_arcsec2=data["solid_angle_arcsec2"],
                )
        return _GRID


def _cell(knots: np.ndarray, pixel: int) -> tuple[int, float]:
    """Grid cell that contains `pixel` and how far into it the pixel is (0 = first knot, 1 = next)."""
    i = int(np.searchsorted(knots, pixel, side="right")) - 1
    i = min(max(i, 0), len(knots) - 2)
    return i, (pixel - knots[i]) / (knots[i + 1] - knots[i])


def _bilinear(values: np.ndarray, i: int, ti: float, j: int, tj: float) -> float:
    """Value inside cell (i, j) of a 2-D grid; ti along rows, tj along columns."""
    top = values[i, j] * (1 - tj) + values[i, j + 1] * tj
    bottom = values[i + 1, j] * (1 - tj) + values[i + 1, j + 1] * tj
    return float(top * (1 - ti) + bottom * ti)


def at(detector: int, x_px: float, y_px: float) -> PixelCalibration:
    """Values of the pixel that contains detector position (x_px, y_px), 0-based, full detector."""
    g = grid()
    last = int(g.knots_px[-1])
    row = min(max(int(round(y_px)), 0), last)
    col = min(max(int(round(x_px)), 0), last)
    i, ti = _cell(g.knots_px, row)
    j, tj = _cell(g.knots_px, col)
    d = detector - 1
    return PixelCalibration(
        lambda_um=_bilinear(g.lambda_um[d], i, ti, j, tj),
        bandwidth_um=_bilinear(g.bandwidth_um[d], i, ti, j, tj),
        solid_angle_arcsec2=_bilinear(g.solid_angle_arcsec2[d], i, ti, j, tj),
    )
