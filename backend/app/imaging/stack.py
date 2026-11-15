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

import numpy as np

# Pixels with no data in any image are expected at the field edges. Filters are set once here
# because warnings.catch_warnings() is not safe when two jobs run in different threads.
warnings.filterwarnings("ignore", message="All-NaN slice encountered")


def stack(frames: list[np.ndarray]) -> np.ndarray:
    """Per-pixel median of aligned, background-subtracted images, ignoring NaN (no data)."""
    return np.nanmedian(np.stack(frames).astype(np.float32), axis=0).astype(np.float32)


def difference(later: np.ndarray, earlier: np.ndarray) -> np.ndarray:
    """later − earlier: what appeared is positive, what left is negative."""
    return (later - earlier).astype(np.float32)
