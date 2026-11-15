"""The common grid every image of a request is put on: north up, east left, centred on the position.

Ported from the blink notebook (cell 7). The grid is also the single place that converts sky
positions to places on the displayed image, so markers and overlays line up with the pixels.
"""

from dataclasses import dataclass

import numpy as np
from astropy.wcs import WCS

from ..config import get_settings


@dataclass(frozen=True)
class Grid:
    wcs: WCS
    shape: tuple[int, int]  # (rows, columns)
    ra_deg: float
    dec_deg: float
    fov_arcmin: float
    pixel_scale_arcsec: float

    def describe(self) -> dict:
        return {
            "ra_deg": self.ra_deg,
            "dec_deg": self.dec_deg,
            "fov_arcmin": self.fov_arcmin,
            "pixel_scale_arcsec": self.pixel_scale_arcsec,
            "width_px": self.shape[1],
            "height_px": self.shape[0],
            "orientation": "north up, east left",
        }


def make_grid(ra_deg: float, dec_deg: float, fov_arcmin: float) -> Grid:
    s = get_settings()
    scale_arcsec = s.pixel_scale_arcsec / max(1, s.output_oversample)
    side_px = max(2, round(fov_arcmin * 60 / scale_arcsec))
    step_deg = fov_arcmin / 60 / side_px
    wcs = WCS(naxis=2)
    wcs.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    wcs.wcs.radesys = "ICRS"
    wcs.wcs.crval = [ra_deg, dec_deg]
    wcs.wcs.crpix = [(side_px + 1) / 2, (side_px + 1) / 2]
    wcs.wcs.cdelt = [-step_deg, step_deg]
    wcs.wcs.cunit = ["deg", "deg"]
    return Grid(wcs, (side_px, side_px), ra_deg, dec_deg, fov_arcmin, step_deg * 3600)


def to_fraction(grid: Grid, ra_deg, dec_deg) -> tuple[np.ndarray, np.ndarray]:
    """Sky position → place on the displayed image as fractions: (0, 0) is the top-left corner,
    (1, 1) the bottom-right. Values outside 0–1 are outside the field. Accepts arrays."""
    x, y = grid.wcs.world_to_pixel_values(np.asarray(ra_deg, float), np.asarray(dec_deg, float))
    rows, cols = grid.shape
    return (x + 0.5) / cols, 1.0 - (y + 0.5) / rows
