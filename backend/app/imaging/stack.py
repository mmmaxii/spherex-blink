"""Adding and subtracting aligned images.

A stack is the per-pixel median of the images of a survey pass. Only detector defects are hidden
(flags.DETECTOR_DEFECTS: dead, hot and cold pixels); pixels flagged around stars keep their
value. Why, measured on RW Aur and eps Ind B (15 Nov 2026):
- hidden pixels form blobs around stars that change from image to image; averaging the images
  that remain made flat patches with stair-step edges in every difference;
- one image with an odd background (RW Aur, pass 1: 90th percentile 0.67 MJy/sr against ~0.2)
  pulled a mean into a bright band across the field; the median ignores it;
- the median removes a cosmic ray present in one image even with 3–4 images, where a 3-sigma
  clip cannot reject it (one outlier among four is only 2.3 sigma away). A hot pixel can sit on
  the same sky spot in every image of a pass, which is why defects are still hidden.
The median is ~25 % noisier than a mean of clean images; for pictures this is the better trade.
Images of one detector see the position at different wavelengths, so a stack is a broad-band
image of that detector's range. Stacks are only drawn, never measured.
"""

import warnings
from dataclasses import dataclass

import numpy as np
from astropy.stats import mad_std
from scipy.ndimage import gaussian_filter

# Pixels with no data in any image are expected at the field edges. Filters are set once here
# because warnings.catch_warnings() is not safe when two jobs run in different threads.
warnings.filterwarnings("ignore", message="All-NaN slice encountered")


def stack(frames: list[np.ndarray]) -> np.ndarray:
    """Per-pixel median of aligned, background-subtracted images, ignoring NaN (no data)."""
    return np.nanmedian(np.stack(frames).astype(np.float32), axis=0).astype(np.float32)


def difference(later: np.ndarray, earlier: np.ndarray) -> np.ndarray:
    """later − earlier: what appeared is positive, what left is negative."""
    return (later - earlier).astype(np.float32)


# --- What changed, relative to each star's own brightness ----------------------------------------
#
# A plain difference leaves a white–black pair on every star, even constant ones: SPHEREx images a
# star on very few pixels, and the shape of that image changes with wavelength and detector place
# from one pass to the next (alignment itself is good to 0.1 px, measured on RW Aur). Those pairs
# are a few % of each star, but a ±6σ scale shows them all at full contrast. Dividing the change by
# the star's own brightness, after a light blur that evens out the shapes, leaves constant stars
# near 0 and shows what really changed: on RW Aur (D1, pass 3 − pass 1) only RW Aur passes 27 %.

STAR_SIGMA = 8.0  # pixels brighter than this many sky sigmas count as "on a star"
SMOOTHING_PX = 1.5  # Gaussian sigma in grid pixels (4.6″ with 3.08″ pixels; the PSF FWHM is ~9″)
MIN_THRESHOLD = 0.10  # never call a change below 10 % real, whatever the constant stars show


@dataclass
class Change:
    relative: np.ndarray  # (later − earlier) / their mean, on star pixels; NaN elsewhere
    has_data: np.ndarray  # True where both stacks have data
    threshold: float  # changes below this are what constant stars show: drawn as "no change"


def _blur(data: np.ndarray, sigma_px: float) -> np.ndarray:
    """Gaussian blur that ignores NaN (normalised convolution); NaN stays where there was no data."""
    valid = np.isfinite(data)
    blurred = gaussian_filter(np.where(valid, data, 0.0), sigma_px)
    weight = gaussian_filter(valid.astype(np.float64), sigma_px)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = blurred / weight
    out[~valid] = np.nan
    return out.astype(np.float32)


def relative_change(later: np.ndarray, earlier: np.ndarray, smoothing_px: float = SMOOTHING_PX) -> Change:
    """How much each star changed, as a fraction of its own brightness (0.2 = 20 % brighter later).
    The threshold is 3 times the scatter of all star pixels (mostly constant stars), at least 10 %."""
    a, b = _blur(earlier, smoothing_px), _blur(later, smoothing_px)
    has_data = np.isfinite(a) & np.isfinite(b)
    mean = (a + b) / 2
    noise = float(mad_std(a[has_data])) if has_data.any() else 0.0
    on_star = has_data & (mean > STAR_SIGMA * noise) if noise > 0 else np.zeros_like(has_data)
    relative = np.full(a.shape, np.nan, dtype=np.float32)
    relative[on_star] = (b[on_star] - a[on_star]) / mean[on_star]
    scatter = float(mad_std(relative[on_star])) if on_star.sum() > 10 else 0.0
    return Change(relative, has_data, max(3.0 * scatter, MIN_THRESHOLD))
