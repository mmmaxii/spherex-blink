"""Putting a cutout (detector orientation, TAN-SIP) on the common grid.

Ported from the blink notebook (cell 7), which used reproject_interp. `reproject_method = "exact"`
switches to the flux-conserving reprojection IRSA uses; needed before measuring flux on aligned
images (VERIFY against the notebook before using aligned images for photometry).
"""

import numpy as np
from astropy.wcs import WCS
from reproject import reproject_exact, reproject_interp

from ..config import get_settings
from .grid import Grid


def align(image: np.ndarray, wcs: WCS, grid: Grid, method: str | None = None) -> np.ndarray:
    """Image on the grid, float32, NaN where the image has no data."""
    method = method or get_settings().reproject_method
    if method == "exact":
        data, footprint = reproject_exact((image, wcs), grid.wcs, shape_out=grid.shape, parallel=False)
    else:
        data, footprint = reproject_interp((image, wcs), grid.wcs, shape_out=grid.shape)
    data = np.asarray(data, dtype=np.float32)
    data[(footprint <= 0) | ~np.isfinite(data)] = np.nan
    return data


def align_mask(mask: np.ndarray, wcs: WCS, grid: Grid) -> np.ndarray:
    """Boolean mask on the grid (nearest pixel); False outside the image."""
    data, footprint = reproject_interp(
        (mask.astype(np.float32), wcs), grid.wcs, shape_out=grid.shape, order="nearest-neighbor"
    )
    return (np.nan_to_num(data) > 0.5) & (footprint > 0)
