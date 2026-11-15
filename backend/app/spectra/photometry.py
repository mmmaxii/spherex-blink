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
"""

import math
from dataclasses import asdict, dataclass

import numpy as np
from astropy.stats import sigma_clipped_stats
from photutils.aperture import CircularAnnulus, CircularAperture

from ..config import get_settings
from ..data import calibration
from ..data import flags as flaglib
from ..data.l2 import Cutout, FrameSkipped

IMPLEMENTED = False

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


def _recipe_flags_in(cutout: Cutout, where: np.ndarray) -> list[str]:
    """Names of the recipe flags set on the pixels selected by `where` (for the skip reason)."""
    if cutout.flags is None:
        return []
    names: set[str] = set()
    for row, col in np.argwhere(where):
        names.update(flaglib.names_at(cutout.flags, cutout.flag_bits, int(row), int(col)))
    return sorted(n for n in names if n in flaglib.EXCLUDE_FOR_PHOTOMETRY)


def measure(cutout: Cutout) -> Measurement:
    """Forced aperture photometry at (cutout.x_px, cutout.y_px). Raises FrameSkipped with a
    readable reason when this image cannot give a trustworthy flux."""
    s = get_settings()
    image = cutout.image_mjysr.astype(np.float64)
    x, y = cutout.x_px, cutout.y_px
    edge = s.background_outer_px + 1
    if not (edge <= x < image.shape[1] - edge and edge <= y < image.shape[0] - edge):
        raise FrameSkipped("target too close to the detector edge")

    bad = ~np.isfinite(image)
    if cutout.flags is not None:
        bad |= flaglib.bad_mask(cutout.flags, cutout.flag_bits)

    ring = CircularAnnulus((x, y), s.background_inner_px, s.background_outer_px)
    in_ring = ring.to_mask(method="center").to_image(image.shape) > 0
    sky_values = image[in_ring & ~bad]
    if len(sky_values) < MIN_SKY_PX:
        raise FrameSkipped("not enough clean sky around the target")
    _, sky, sky_std = sigma_clipped_stats(sky_values, sigma=3.0)

    weight = CircularAperture((x, y), s.aperture_radius_px).to_mask(method="exact").to_image(image.shape)
    yy, xx = np.mgrid[: image.shape[0], : image.shape[1]]
    psf = np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * s.psf_sigma_px**2)) * weight
    lost = float(psf[bad].sum() / psf.sum())
    if lost > s.max_lost_light:
        names = _recipe_flags_in(cutout, bad & (weight > 0))
        reason = f"{100 * lost:.0f} % of the star's light falls on flagged pixels"
        raise FrameSkipped(f"{reason} ({', '.join(names)})" if names else reason)

    good = (weight > 0) & ~bad
    total = float(np.sum((image - sky)[good] * weight[good])) / (1 - lost)
    area = float(weight.sum())
    if cutout.variance is not None:
        pixel_var = float(np.sum(cutout.variance[good] * weight[good] ** 2)) / (1 - lost) ** 2
    else:
        pixel_var = area * sky_std**2
    sky_var = area**2 * sky_std**2 / len(sky_values)  # uncertainty of the sky level itself

    lambda_um, bandwidth_um, omega_arcsec2, source = _pixel_calibration(cutout)
    to_mjy = omega_arcsec2 * ARCSEC2_TO_SR * 1e9  # MJy/sr summed over pixels -> mJy
    flux_mjy = total * to_mjy
    stat_err_mjy = math.sqrt(pixel_var + sky_var) * to_mjy
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
        background_mjysr=float(sky),
        n_bad_px=int(((weight > 0) & bad).sum()),
        lost_fraction=lost,
        flags=flaglib.names_at(cutout.flags, cutout.flag_bits, round(y), round(x))
        if cutout.flags is not None
        else [],
        lambda_source=source,
    )
