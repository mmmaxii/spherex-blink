"""The variability pipeline: a sky position → its light curve, compared with constant stars around it.

Steps:
  1. search     every image of the position, wide and deep surveys (the deep fields near the ecliptic
                poles are observed almost continuously: that is what gives periods)   data/sia.py
  2. thin       at most `variability_max_images`, spread evenly in time
  3. compare    comparison stars detected in a sample of images                       spectra/variability.py
  4. measure    target (aperture, or PSF wings when saturated) and comparison stars on every image
  5. analyse    residuals at the same wavelength, scatter vs constant stars, passes, bands, period
"""

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

from ..config import get_settings
from ..core.cache import make_key
from ..core.jobs import Job, Progress
from ..core.products import get_product_store
from ..data import sia
from ..data.l2 import Cutout
from ..data.resolve import propagate
from ..errors import NoCoverage, NotEnoughFrames
from ..spectra import variability
from .common import for_each_image, read_cutout_with_retries, start_job, weekly_tag

KIND = "variability"
PIPELINE_VERSION = "1"
SAMPLE_IMAGES = 16  # images used to find the comparison stars

NOTES = [
    "Each point is the target on one image divided by the same target at the same wavelength in the "
    "other images: a constant star stays around 1.",
    "Grey points are comparison stars from the same images: their scatter is what noise looks like here.",
    "Saturated stars are followed with the wings of their image (relative units). That method cannot "
    "see changes smaller than ~15 %.",
    "Each image sees the star at one wavelength: a colour change shows up as passes that disagree in "
    "some bands and not in others (table by band).",
]


@dataclass(frozen=True)
class VariabilityParams:
    ra_deg: float  # with proper motion, the position at epoch_mjd
    dec_deg: float
    pm_ra_masyr: float = 0.0
    pm_dec_masyr: float = 0.0
    epoch_mjd: float | None = None

    def key(self) -> str:
        s = get_settings()
        collections = ",".join(s.sia_collections + s.sia_deep_collections)
        return make_key(KIND, PIPELINE_VERSION, weekly_tag(), collections, *asdict(self).values())


def start(params: VariabilityParams) -> Job:
    return start_job(KIND, params.key(), lambda progress: run(params, progress))


def _position(params: VariabilityParams, mjd: float) -> tuple[float, float]:
    """Where the target was on a date (fast stars move by pixels between passes)."""
    if params.epoch_mjd is None or (params.pm_ra_masyr == 0 and params.pm_dec_masyr == 0):
        return params.ra_deg, params.dec_deg
    return propagate(
        params.ra_deg, params.dec_deg, params.pm_ra_masyr, params.pm_dec_masyr, params.epoch_mjd, mjd
    )


def _read(ref: sia.ImageRef, params: VariabilityParams) -> Cutout:
    ra_deg, dec_deg = _position(params, ref.mjd)
    return read_cutout_with_retries(ref, ra_deg, dec_deg, get_settings().variability_cutout_half_px)


def _measure_image(
    ref: sia.ImageRef, params: VariabilityParams, comparisons: list[tuple[float, float]]
) -> list[variability.StarPoint]:
    """Target and comparison stars on one image."""
    cutout = _read(ref, params)
    points = []
    target = variability.measure_star(cutout, 0, cutout.x_px, cutout.y_px, with_wings=True)
    if target:
        points.append(target)
    for number, (ra, dec) in enumerate(comparisons, start=1):
        x, y = (float(v) for v in cutout.wcs.world_to_pixel_values(ra, dec))
        point = variability.measure_star(cutout, number, x, y, with_wings=False)
        if point:
            points.append(point)
    return points


def run(params: VariabilityParams, progress: Progress) -> dict[str, Any]:
    """The whole pipeline. Returns the manifest (schemas.VariabilityResult)."""
    s = get_settings()
    key = params.key()

    progress(0.02, "Searching SPHEREx images (wide and deep surveys)")
    images = sia.search(params.ra_deg, params.dec_deg, s.sia_collections + s.sia_deep_collections)
    if not images:
        raise NoCoverage("SPHEREx has no public images of this position yet.")
    step = max(1, -(-len(images) // s.variability_max_images))  # ceil division: thin out evenly
    refs = images[::step]

    sample = [refs[i] for i in np.linspace(0, len(refs) - 1, min(SAMPLE_IMAGES, len(refs))).astype(int)]
    cutouts, _ = for_each_image(
        sample, lambda ref: _read(ref, params), progress, (0.04, 0.14), "Finding comparison stars"
    )
    ra_now, dec_now = _position(params, float(np.median([r.mjd for r in refs])))
    max_radius_arcsec = (s.variability_cutout_half_px - 12) * s.pixel_scale_arcsec
    comparisons = variability.choose_comparisons(
        [variability.detect_sources(c) for c in cutouts], ra_now, dec_now, max_radius_arcsec
    )

    measured, skipped = for_each_image(
        refs, lambda ref: _measure_image(ref, params, comparisons), progress, (0.14, 0.94), "Measuring images"
    )
    points = [p for image_points in measured for p in image_points]
    n_target = sum(p.star == 0 for p in points)
    if n_target < 10:
        raise NotEnoughFrames(
            f"The target was measured on only {n_target} images: too few for a light curve.",
            detail={"skipped": skipped},
        )

    progress(0.96, "Comparing with the constant stars")
    analysis = variability.analyse(points)
    manifest = {
        "kind": KIND,
        "key": key,
        "params": asdict(params),
        "collections": s.sia_collections + s.sia_deep_collections,
        "n_images": len(refs),
        "n_available": len(images),
        **analysis,
        "method": variability.settings_summary(),
        "skipped": skipped,
        "notes": NOTES,
    }
    get_product_store().new_folder(KIND, key)
    get_product_store().save_manifest(KIND, key, manifest)
    return manifest
