"""Flux of the target on one L2 image: one point of its spectrum.

NOT BUILT YET — the method is being worked out in validation/notebooks/maxi/02_spectrum.ipynb.
Everything around it is in place: pipeline/spectrum.py finds the images, reads a cutout with flags
and variance for each one, calls `measure()` and assembles the spectrum per survey pass.

To switch the feature on: write `measure()`, validate it (injection-recovery, a source with a
published spectrum), then set IMPLEMENTED = True. Until then /api/spectrum answers 501.
"""

from dataclasses import asdict, dataclass

from ..data.l2 import Cutout
from ..errors import NotBuilt

IMPLEMENTED = False


@dataclass(frozen=True)
class Measurement:
    """One spectral point. Field names follow data/eps_ind_b_spectrum.ecsv from the notebook."""

    mjd: float
    detector: int
    collection: str
    obs_id: str
    pass_index: int
    lambda_um: float
    bandwidth_um: float
    flux_mjy: float  # millijansky
    flux_err_mjy: float  # millijansky, statistical; the 3 % systematic is added when plotting
    background_mjysr: float
    n_bad_px: int  # flagged pixels inside the aperture
    flags: list[str]  # flag names on the central pixel

    def to_dict(self) -> dict:
        return asdict(self)


def measure(cutout: Cutout) -> Measurement:
    """Forced photometry at (cutout.x_px, cutout.y_px).

    Available in `cutout`: image_mjysr, variance, flags + flag_bits (use
    data.flags.bad_mask for the official recipe), wcs, lambda_um, bandwidth_um, psf_fwhm_arcsec.
    Reminders: MJy/sr → Jy needs the pixel solid angle (6.15")²; SPHEREx is undersampled
    (PSF ~9" on 6.15" pixels), so aperture corrections depend on the sub-pixel position.
    """
    raise NotBuilt("Spectra from the images are not available yet.")
