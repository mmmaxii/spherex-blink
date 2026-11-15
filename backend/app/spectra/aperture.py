"""Which pixels an aperture covers, and how much of each: the two shapes the photometry needs.

Written here instead of importing photutils (which brings scipy along: ~35 MB of memory for two
functions). Both follow photutils' conventions and were checked against photutils 3.1 on 20 000
random positions (equal to 1e-12, see tests/test_spectra.py):

- `circle_weights`: fraction of each pixel inside a circle, computed exactly (photutils "exact").
- `annulus_mask`: pixels whose centre falls inside a ring (photutils "center").

Pixel (row j, column i) covers x in [i - 0.5, i + 0.5] and y in [j - 0.5, j + 0.5]; positions are
0-based, as everywhere in this package.
"""

import math

import numpy as np

HALF_DIAGONAL = math.sqrt(0.5)  # distance from a pixel's centre to its corners
SNAP = 1e-11  # overlaps closer than this to 0 or 1 are rounding, not geometry


def _area_left_and_below(a: np.ndarray, y: np.ndarray, r: float) -> np.ndarray:
    """Area of the circle of radius r centred at (0, 0) with X < a and Y < y (element-wise).

    The circle's vertical chord at X runs from -h to h, h = sqrt(r² - X²). Below the line Y = y it
    keeps clip(y, -h, h) + h of that chord. Where |X| < s = sqrt(r² - y²) the line cuts the chord;
    outside, the chord is whole (y > 0) or gone (y < 0). Integrating with the primitive of h
    gives the closed form below."""

    def h_integral(x):  # ∫_{-r}^{x} sqrt(r² - X²) dX, for -r <= x <= r
        x = np.clip(x, -r, r)
        root = np.sqrt(np.maximum(r * r - x * x, 0.0))
        return 0.5 * (x * root + r * r * np.arcsin(x / r)) + 0.25 * math.pi * r * r

    s = np.sqrt(np.maximum(r * r - y * y, 0.0))
    inside = np.clip(a, -s, s)  # the part of [-r, a] where the line Y = y cuts the chord
    area = y * (inside + s) + h_integral(inside) - h_integral(-s)
    whole_chords = 2 * h_integral(np.clip(a, -r, -s)) + 2 * (h_integral(np.clip(a, s, r)) - h_integral(s))
    return area + np.where(y >= 0, whole_chords, 0.0)


def circle_weights(shape: tuple[int, int], x: float, y: float, r: float) -> np.ndarray:
    """Fraction of each pixel of an array of `shape` that lies inside the circle (x, y, r)."""
    rows, cols = np.mgrid[: shape[0], : shape[1]]
    dx, dy = cols - x, rows - y  # pixel centre relative to the circle centre
    distance = np.hypot(dx, dy)
    weights = np.zeros(shape)
    weights[distance < r - HALF_DIAGONAL] = 1.0  # whole pixel inside (as photutils decides it)
    edge = (distance >= r - HALF_DIAGONAL) & (distance < r + HALF_DIAGONAL)
    x0, x1, y0, y1 = dx[edge] - 0.5, dx[edge] + 0.5, dy[edge] - 0.5, dy[edge] + 0.5
    area = (
        _area_left_and_below(x1, y1, r)
        - _area_left_and_below(x0, y1, r)
        - _area_left_and_below(x1, y0, r)
        + _area_left_and_below(x0, y0, r)
    )
    # Rounding leaves ~1e-13 where a pixel corner only touches the circle: photutils gives 0 (or 1)
    # there, and the photometry counts pixels with weight > 0, so snap those values.
    area = np.where(area < SNAP, 0.0, np.where(area > 1.0 - SNAP, 1.0, area))
    weights[edge] = area
    return weights


def annulus_mask(shape: tuple[int, int], x: float, y: float, r_in: float, r_out: float) -> np.ndarray:
    """True for pixels whose centre lies in the ring r_in <= distance < r_out."""
    rows, cols = np.mgrid[: shape[0], : shape[1]]
    distance2 = (cols - x) ** 2 + (rows - y) ** 2
    return (distance2 >= r_in * r_in) & (distance2 < r_out * r_out)
