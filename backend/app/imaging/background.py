"""Local background of a cutout.

L2 images include the zodiacal light, which changes with date and wavelength; without removing a
level per image, a blink would flash and a stack would be dominated by it. For display and stacks
the sigma-clipped median of the cutout is subtracted. This is not the background model for
photometry (that needs a local annulus; see spectra/photometry.py).
"""

import numpy as np
from astropy.stats import sigma_clipped_stats


def estimate(image: np.ndarray, bad: np.ndarray | None = None) -> tuple[float, float]:
    """(level, noise) in the units of the image; flagged and non-finite pixels are left out."""
    mask = ~np.isfinite(image)
    if bad is not None:
        mask |= bad
    if mask.all():
        return float("nan"), float("nan")
    _, median, std = sigma_clipped_stats(image, mask=mask, sigma=3.0, maxiters=5)
    return float(median), float(std)
