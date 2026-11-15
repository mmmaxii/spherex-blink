"""Adding and subtracting aligned images.

First version: sigma-clipped mean, every image with the same weight. Images of one detector see
the position at different wavelengths, so a stack is a broad-band image of that detector's range.
VERIFY (validation notebook pending): the S/N gain against sqrt(N), and whether inverse-variance
weights are worth it.
"""

import warnings

import numpy as np
from astropy.stats import sigma_clip

from ..config import get_settings

# Pixels with no data in any image are expected at the field edges. Filters are set once here
# because warnings.catch_warnings() is not safe when two jobs run in different threads.
warnings.filterwarnings("ignore", message="Mean of empty slice")
warnings.filterwarnings("ignore", message="All-NaN slice encountered")
warnings.filterwarnings("ignore", message="Input data contains invalid values")


def stack(frames: list[np.ndarray], sigma: float | None = None) -> np.ndarray:
    """Mean of aligned, background-subtracted images, ignoring NaN and (with 3 or more images)
    values further than `sigma` standard deviations from the rest (cosmic rays, moving objects)."""
    sigma = sigma or get_settings().stack_sigma_clip
    cube = np.stack(frames).astype(np.float32)
    if len(frames) >= 3:
        cube = sigma_clip(cube, sigma=sigma, maxiters=3, axis=0, masked=False, copy=True)
    return np.nanmean(cube, axis=0).astype(np.float32)


def difference(later: np.ndarray, earlier: np.ndarray) -> np.ndarray:
    """later − earlier: what appeared is positive, what left is negative."""
    return (later - earlier).astype(np.float32)
