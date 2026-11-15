"""The spectrum pipeline: a sky position → one spectrum per survey pass → what kind of object it is.

Steps:
  1. search     every image covering the position, all detectors         data/sia.py
  2. read       a small cutout of each image with flags and variance     data/l2.py
  3. measure    flux of the target on each image = one spectral point    spectra/photometry.py (NOT BUILT)
  4. assemble   points sorted by wavelength, grouped by survey pass
  5. classify   trained model applied to the spectrum, if one is installed spectra/classifier.py (NOT BUILT)

Steps 1, 2 and 4 work today. While step 3 is a stub, `start()` answers 501 instead of queueing a
job that cannot finish. Comparing passes at the same wavelength is what shows a variable star.
"""

from dataclasses import asdict, dataclass
from typing import Any, Literal

from ..config import get_settings
from ..core.cache import make_key
from ..core.jobs import Job, Progress
from ..core.products import get_product_store
from ..data import sia
from ..data.resolve import propagate
from ..errors import NoCoverage, NotBuilt, NotEnoughFrames
from ..spectra import classifier, photometry
from .common import for_each_image, mjd_to_iso, read_cutout_with_retries, start_job, weekly_tag

KIND = "spectrum"
PIPELINE_VERSION = "1"

NOTES = [
    "Each point is one image: the target is seen at one wavelength per detector and exposure.",
    "Error bars are statistical; SPHEREx's absolute calibration adds about 3 %.",
]


@dataclass(frozen=True)
class SpectrumParams:
    """What defines one spectrum request. "cube" (all-sky cube quick look) is reserved."""

    ra_deg: float  # with proper motion, the position at epoch_mjd
    dec_deg: float
    mode: Literal["pass", "cube"] = "pass"
    pm_ra_masyr: float = 0.0
    pm_dec_masyr: float = 0.0
    epoch_mjd: float | None = None

    def key(self) -> str:
        s = get_settings()
        return make_key(
            KIND, PIPELINE_VERSION, weekly_tag(), ",".join(s.sia_collections), *asdict(self).values()
        )


def is_ready() -> bool:
    """True once the photometry has been written and validated (reported by /api/health)."""
    return photometry.IMPLEMENTED


def start(params: SpectrumParams) -> Job:
    """Queue the spectrum, or answer 501 while a step it needs does not exist."""
    if params.mode == "cube":
        raise NotBuilt("Quick-look spectra from the all-sky cube are not available yet.")
    if not is_ready():
        raise NotBuilt("Spectra from the images are not available yet.")
    return start_job(KIND, params.key(), lambda progress: run(params, progress))


def _position(params: SpectrumParams, mjd: float) -> tuple[float, float]:
    """Where the target was on a date (fast stars move by pixels between passes)."""
    if params.epoch_mjd is None or (params.pm_ra_masyr == 0 and params.pm_dec_masyr == 0):
        return params.ra_deg, params.dec_deg
    return propagate(
        params.ra_deg, params.dec_deg, params.pm_ra_masyr, params.pm_dec_masyr, params.epoch_mjd, mjd
    )


def _measure(ref: sia.ImageRef, params: SpectrumParams) -> dict[str, Any]:
    """Steps 2–3 for one image: the cutout is centred where the target was on that date."""
    ra_deg, dec_deg = _position(params, ref.mjd)
    cutout = read_cutout_with_retries(
        ref, ra_deg, dec_deg, get_settings().spectrum_cutout_half_px, with_variance=True
    )
    point = photometry.measure(cutout).to_dict()
    point["date_utc"] = mjd_to_iso(point["mjd"])
    return point


def run(params: SpectrumParams, progress: Progress) -> dict[str, Any]:
    """The whole pipeline. Returns the manifest (schemas.SpectrumResult)."""
    s = get_settings()
    key = params.key()

    progress(0.02, "Searching SPHEREx images")
    images = sia.search(params.ra_deg, params.dec_deg)
    if not images:
        raise NoCoverage("SPHEREx has no public images of this position yet.")
    step = max(1, -(-len(images) // s.spectrum_max_images))  # ceil division: thin out evenly if too many
    refs = images[::step]

    points, skipped = for_each_image(
        refs, lambda ref: _measure(ref, params), progress, (0.05, 0.92), "Measuring images"
    )
    if len(points) < 3:
        raise NotEnoughFrames(
            f"Only {len(points)} of {len(refs)} images gave a measurement.", detail={"skipped": skipped}
        )
    points.sort(key=lambda p: p["lambda_um"])

    # Step 4: one group of points per survey pass, to compare passes at the same wavelength.
    passes = []
    for index in sorted({p["pass_index"] for p in points}):
        group = [p for p in points if p["pass_index"] == index]
        passes.append(
            {
                "pass_index": index,
                "n_points": len(group),
                "mjd_start": min(p["mjd"] for p in group),
                "mjd_end": max(p["mjd"] for p in group),
            }
        )

    progress(0.95, "Classifying the spectrum")
    # No model installed is not an error: the spectrum is shown without a class.
    try:
        classification = classifier.classify(points)
    except NotBuilt:
        classification = None

    manifest = {
        "kind": KIND,
        "key": key,
        "params": asdict(params),
        "collections": s.sia_collections,
        "points": points,
        "passes": passes,
        "classification": classification.to_dict() if classification else None,
        "skipped": skipped,
        "notes": NOTES,
    }
    get_product_store().new_folder(KIND, key)
    get_product_store().save_manifest(KIND, key, manifest)
    return manifest
