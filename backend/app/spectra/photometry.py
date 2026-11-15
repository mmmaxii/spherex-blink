"""Flux of the target on one L2 image: one point of its spectrum.

Method validated on 15 Nov 2026 with eps Ind B (validation/notebooks/maxi/03 and 04; prototype
scripts 11 and 12; notes in the prototype's docs/espectro_l2_proceso.md):

  1. aperture of 2.5 px around the target (encloses 97.7-98.8 % of the ePSF on all detectors);
  2. sky = sigma-clipped median of a 6-10 px annulus. Only pixels of the official flag recipe are left
     out. SOURCE is NOT left out: in DR1 it covers ~45 % of every detector (Supplement §3.2.9, "pixels
     with significant flux from catalog sources"), and excluding it left no sky at all;
  3. flagged pixels inside the aperture are dropped and the flux is scaled up by the share of the
     star's light they held (Gaussian stand-in for the PSF). Above 20 % lost the image is skipped:
     that is a saturated or damaged core, where the number would not be trustworthy;
  4. wavelength, bandwidth and pixel solid angle of that pixel from the calibration maps
     (data/calibration.py); MJy/sr x sr -> mJy;
  5. error = pixel variance + sky uncertainty, plus 3 % in quadrature (as the official IRSA tool).

Checked results: the four passes of eps Ind B agree within 1 % and the spectrum shows the expected
T-dwarf bands; injected 10 % sinusoids come back as 9.5 % with the right period.
Not handled here: saturated stars (Barnard, R Dra, parts of RW Aur). Their light can be followed
with the PSF wings, but only in relative units (notebook 04), so they get no mJy point here.

Every step works on a small window around the target (the sky annulus plus a margin), not on the
whole cutout: the numbers are the same and a 301 x 301 cutout with 30 comparison stars costs ~150
times less memory and CPU. Aperture shapes come from spectra/aperture.py (photutils conventions).
"""

import math
from dataclasses import asdict, dataclass

import numpy as np
from astropy.stats import sigma_clipped_stats

from ..config import get_settings
from ..data import calibration
from ..data import flags as flaglib
from ..data.l2 import Cutout, FrameSkipped
from .aperture import annulus_mask, circle_weights

IMPLEMENTED = True  # validated on eps Ind B, 15 Nov 2026 (see the module docstring)

ARCSEC2_TO_SR = (math.pi / 180 / 3600) ** 2
MIN_SKY_PX = 15  # clean annulus pixels needed for a sky level


@dataclass(frozen=True)
class Measurement:
    """One spectral point: the target on one image, at one wavelength and one date."""

    mjd: float
    detector: int
    collection: str
    obs_id: str
    pass_index: int
    lambda_um: float
    bandwidth_um: float
    flux_mjy: float  # millijansky
    flux_err_mjy: float  # statistical (+) 3 % calibration, in quadrature
    stat_err_mjy: float  # statistical part only
    background_mjysr: float
    n_bad_px: int  # flagged pixels inside the aperture (left out)
    lost_fraction: float  # share of the star's light on those pixels (the flux is corrected for it)
    flags: list[str]  # flag names on the central pixel
    lambda_source: str  # "spectral_wcs" (science) or "wcs-wave" (fallback, approximate)
    suspect: bool = False  # set by the pipeline: far from the same-pass points at the same wavelength

    def to_dict(self) -> dict:
        return asdict(self)


def _pixel_calibration(cutout: Cutout) -> tuple[float, float, float, str]:
    """(lambda_um, bandwidth_um, solid_angle_arcsec2, source). Falls back to the file's own values
    if the calibration maps cannot be read, and says so."""
    try:
        cal = calibration.at(cutout.ref.detector, cutout.detector_x_px, cutout.detector_y_px)
        return cal.lambda_um, cal.bandwidth_um, cal.solid_angle_arcsec2, "spectral_wcs"
    except Exception:  # noqa: BLE001 - network or file errors: keep measuring with the header values
        omega = cutout.pixel_solid_angle_arcsec2 or get_settings().pixel_scale_arcsec ** 2
        return cutout.lambda_um, cutout.bandwidth_um, omega, "wcs-wave"


@dataclass(frozen=True)
class Window:
    """The pixels of a cutout around one position: everything the photometry looks at."""

    image: np.ndarray  # float64 [MJy/sr]
    bad: np.ndarray  # True = no value or a flag of the official recipe
    flags: np.ndarray | None
    variance: np.ndarray | None
    x: float  # the position, in window pixels
    y: float


def window(cutout: Cutout, x: float, y: float, radius_px: float) -> Window:
    """Every pixel whose centre is within `radius_px` of cutout position (x, y), plus one pixel of
    margin (clipped at the cutout edges). Slices of the cutout: nothing outside is copied."""
    half = math.ceil(radius_px) + 1
    rows, cols = cutout.image_mjysr.shape
    r0, r1 = max(0, int(y) - half), min(rows, int(y) + half + 2)
    c0, c1 = max(0, int(x) - half), min(cols, int(x) + half + 2)
    image = cutout.image_mjysr[r0:r1, c0:c1].astype(np.float64)
    flags = cutout.flags[r0:r1, c0:c1] if cutout.flags is not None else None
    bad = ~np.isfinite(image)
    if flags is not None:
        bad |= flaglib.bad_mask(flags, cutout.flag_bits)
    variance = cutout.variance[r0:r1, c0:c1] if cutout.variance is not None else None
    return Window(image, bad, flags, variance, x - c0, y - r0)


def _recipe_flags_in(flags: np.ndarray | None, bits: dict[int, str], where: np.ndarray) -> list[str]:
    """Names of the recipe flags set on the pixels selected by `where` (for the skip reason)."""
    if flags is None:
        return []
    names: set[str] = set()
    for row, col in np.argwhere(where):
        names.update(flaglib.names_at(flags, bits, int(row), int(col)))
    return sorted(n for n in names if n in flaglib.EXCLUDE_FOR_PHOTOMETRY)


@dataclass(frozen=True)
class _Sky:
    level_mjysr: float  # sigma-clipped median of the annulus
    std_mjysr: float  # pixel-to-pixel scatter of the sky
    n_px: int  # clean pixels used


def _sky(image: np.ndarray, bad: np.ndarray, x: float, y: float) -> _Sky:
    """Sky level in the annulus around the target. Recipe-flagged pixels are left out; neighbour
    stars that fall in the annulus are removed by the 3-sigma clipping (SOURCE is not left out)."""
    s = get_settings()
    in_annulus = annulus_mask(image.shape, x, y, s.background_inner_px, s.background_outer_px)
    values = image[in_annulus & ~bad]
    if len(values) < MIN_SKY_PX:
        raise FrameSkipped("not enough clean sky around the target")
    _, median, std = sigma_clipped_stats(values, sigma=3.0)
    return _Sky(level_mjysr=float(median), std_mjysr=float(std), n_px=len(values))


def _aperture_weights(shape: tuple[int, int], x: float, y: float) -> np.ndarray:
    """Fraction of each pixel inside the aperture circle (0 outside, 1 inside, partial at the edge)."""
    return circle_weights(shape, x, y, get_settings().aperture_radius_px)


def _light_on_bad_pixels(weights: np.ndarray, bad: np.ndarray, x: float, y: float) -> float:
    """Share of the star's light in the aperture that falls on bad pixels, using a Gaussian of the
    PSF width as the star's shape. 0 = no light lost, 1 = the whole core is flagged."""
    yy, xx = np.mgrid[: weights.shape[0], : weights.shape[1]]
    sigma = get_settings().psf_sigma_px
    star = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * sigma**2)) * weights
    return float(star[bad].sum() / star.sum())


def measure(cutout: Cutout) -> Measurement:
    """Forced aperture photometry at (cutout.x_px, cutout.y_px). Raises FrameSkipped with a
    readable reason when this image cannot give a trustworthy flux."""
    s = get_settings()
    rows, cols = cutout.image_mjysr.shape

    # 1. The aperture and the sky annulus must fit inside the cutout.
    margin = s.background_outer_px + 1
    if not (margin <= cutout.x_px < cols - margin and margin <= cutout.y_px < rows - margin):
        raise FrameSkipped("target too close to the detector edge")

    # 2. Pixels to leave out, and the sky level around the target (all inside the window).
    w = window(cutout, cutout.x_px, cutout.y_px, s.background_outer_px)
    image, bad, x, y = w.image, w.bad, w.x, w.y
    sky = _sky(image, bad, x, y)

    # 3. How much of the star's light is on bad pixels. Too much = saturated or damaged core.
    weights = _aperture_weights(image.shape, x, y)
    lost = _light_on_bad_pixels(weights, bad, x, y)
    if lost > s.max_lost_light:
        names = _recipe_flags_in(w.flags, cutout.flag_bits, bad & (weights > 0))
        reason = f"{100 * lost:.0f} % of the star's light falls on flagged pixels"
        raise FrameSkipped(f"{reason} ({', '.join(names)})" if names else reason)

    # 4. Sum of (pixel - sky) over the good pixels, scaled up for the light that the bad ones held.
    good = (weights > 0) & ~bad
    total_mjysr_px = float(np.sum((image - sky.level_mjysr)[good] * weights[good])) / (1 - lost)

    # 5. Statistical error: pixel noise (from the VARIANCE extension when it was read) plus the
    #    uncertainty of the sky level that was subtracted from every aperture pixel.
    area_px = float(weights.sum())
    if w.variance is not None:
        pixel_var = float(np.sum(w.variance[good] * weights[good] ** 2)) / (1 - lost) ** 2
    else:
        pixel_var = area_px * sky.std_mjysr**2
    sky_var = area_px**2 * sky.std_mjysr**2 / sky.n_px

    # 6. Wavelength of this pixel and conversion MJy/sr x (pixel solid angle) -> mJy.
    lambda_um, bandwidth_um, omega_arcsec2, source = _pixel_calibration(cutout)
    to_mjy = omega_arcsec2 * ARCSEC2_TO_SR * 1e9
    flux_mjy = total_mjysr_px * to_mjy
    stat_err_mjy = math.sqrt(pixel_var + sky_var) * to_mjy

    central_flags = []
    if cutout.flags is not None:
        row, col = round(cutout.y_px), round(cutout.x_px)
        central_flags = flaglib.names_at(cutout.flags, cutout.flag_bits, row, col)

    return Measurement(
        mjd=cutout.mjd,
        detector=cutout.ref.detector,
        collection=cutout.ref.collection,
        obs_id=cutout.ref.obs_id,
        pass_index=cutout.ref.pass_index,
        lambda_um=lambda_um,
        bandwidth_um=bandwidth_um,
        flux_mjy=flux_mjy,
        flux_err_mjy=math.hypot(stat_err_mjy, s.calibration_systematic * flux_mjy),
        stat_err_mjy=stat_err_mjy,
        background_mjysr=sky.level_mjysr,
        n_bad_px=int(((weights > 0) & bad).sum()),
        lost_fraction=lost,
        flags=central_flags,
        lambda_source=source,
    )
