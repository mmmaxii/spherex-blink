"""The blink pipeline: a sky position → a series of aligned SPHEREx images "like a little video".

Steps (each one is a function in data/ or imaging/):
  1. search     every image covering the position, all configured releases          data/sia.py
  2. select     images of one detector, spread over the survey passes               data/sia.py
  3. read       a cutout of each image straight from S3, with its flags             data/l2.py
  4. background median level of each cutout removed (zodiacal light)                imaging/background.py
  5. align      every cutout onto one north-up grid centred on the position         imaging/align.py
  6. stack      one stack per survey pass + one of everything; pass − first pass    imaging/stack.py
  7. render     PNG per frame with a common scale, flag overlays, GIF               imaging/render.py

The result (manifest) lists every file with its date, wavelength and quality information.
"""

import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from scipy.ndimage import binary_dilation

from ..config import get_settings
from ..core.cache import make_key
from ..core.jobs import Job, Progress
from ..core.products import get_product_store
from ..data import flags as flaglib
from ..data import l2, sia
from ..data.resolve import propagate
from ..errors import NoCoverage, NotEnoughFrames
from ..imaging import background, render
from ..imaging import stack as stacking
from ..imaging.align import align, align_mask
from ..imaging.grid import Grid, make_grid, to_fraction
from .common import for_each_image, mjd_to_iso, read_cutout_with_retries, start_job, weekly_tag

KIND = "blink"
PIPELINE_VERSION = "3"  # raise it when the output changes, so stored products are not reused

NOTES = [
    "Each image had its median level subtracted (zodiacal light) so frames can be compared.",
    "Pixels flagged by the SPHEREx pipeline (cosmic-ray hits, persistence, halos of bright stars...) "
    "and their immediate neighbours are hidden by default: they change from image to image and look "
    "like moving objects. In the pictures they are filled from the surrounding sky (never in "
    "measurements); 'Paint flags' shows where they are and the unmasked images are available too.",
    "Images of one detector see the position at different wavelengths: a change of brightness "
    "between frames can come from the wavelength, not from time. Check the wavelength of each frame.",
    "Stacks are sigma-clipped means of the images of a survey pass, without flagged pixels.",
    "Differences are a pass stack minus the first pass stack (mid-gray = no change).",
]


@dataclass(frozen=True)
class BlinkParams:
    """What defines one blink. Equal parameters give the same key, so the work is shared."""

    ra_deg: float  # field centre; with proper motion, the position at epoch_mjd
    dec_deg: float
    fov_arcmin: float
    detector: int
    max_frames: int
    pm_ra_masyr: float = 0.0  # includes cos(dec)
    pm_dec_masyr: float = 0.0
    epoch_mjd: float | None = None

    def key(self) -> str:
        s = get_settings()
        return make_key(
            KIND, PIPELINE_VERSION, weekly_tag(), ",".join(s.sia_collections), s.output_oversample,
            s.reproject_method, *asdict(self).values(),
        )  # fmt: skip


@dataclass
class _Frame:
    """One image after steps 3–5, kept in memory until the PNGs are written."""

    ref: sia.ImageRef
    clean: np.ndarray  # background-subtracted, flagged pixels hidden (NaN), on the grid
    raw: np.ndarray  # background-subtracted, everything the detector recorded, on the grid
    bad: np.ndarray  # flagged pixels (official recipe), on the grid
    noise: float
    info: dict[str, Any]


def start(params: BlinkParams) -> Job:
    """Queue the blink (or return the job or stored result of an equal request)."""
    return start_job(KIND, params.key(), lambda progress: run(params, progress))


def target_position(params: BlinkParams, mjd: float) -> tuple[float, float]:
    """Where the target is expected on a date (the field centre when it has no proper motion)."""
    if params.epoch_mjd is None or (params.pm_ra_masyr == 0 and params.pm_dec_masyr == 0):
        return params.ra_deg, params.dec_deg
    return propagate(
        params.ra_deg, params.dec_deg, params.pm_ra_masyr, params.pm_dec_masyr, params.epoch_mjd, mjd
    )


def _load_frame(ref: sia.ImageRef, params: BlinkParams, grid: Grid, half_size_px: int) -> _Frame:
    """Steps 3–5 for one image."""
    s = get_settings()
    cutout = read_cutout_with_retries(ref, params.ra_deg, params.dec_deg, half_size_px)
    bad = flaglib.bad_mask(cutout.flags, cutout.flag_bits)
    hidden = binary_dilation(bad, iterations=s.mask_grow_px) if s.mask_grow_px > 0 else bad
    level, noise = background.estimate(cutout.image_mjysr, hidden)
    if not math.isfinite(level):
        raise l2.FrameSkipped("no valid pixels around the position")

    image = cutout.image_mjysr - level
    raw = align(image, cutout.wcs, grid)
    coverage = float(np.isfinite(raw).mean())
    if coverage < s.min_coverage_fraction:
        raise l2.FrameSkipped(f"covers only {coverage:.0%} of the field")
    clean = align(np.where(hidden, np.nan, image), cutout.wcs, grid)
    bad_on_grid = align_mask(bad, cutout.wcs, grid)

    target_ra, target_dec = target_position(params, cutout.mjd)
    x_frac, y_frac = to_fraction(grid, target_ra, target_dec)
    col, row = (int(round(float(v))) for v in cutout.wcs.world_to_pixel_values(target_ra, target_dec))
    info = {
        "obs_id": ref.obs_id,
        "collection": ref.collection,
        "detector": ref.detector,
        "pass_index": ref.pass_index,
        "mjd": cutout.mjd,
        "date_utc": mjd_to_iso(cutout.mjd),
        "lambda_um": round(cutout.lambda_um, 5),
        "bandwidth_um": round(cutout.bandwidth_um, 5),
        "coverage_fraction": round(coverage, 3),
        "background_mjysr": round(level, 5),
        "noise_mjysr": round(noise, 5),
        "flagged_fraction": round(float(bad.mean()), 4),
        "flag_counts": flaglib.count_flags(cutout.flags, cutout.flag_bits),
        "target_flags": flaglib.names_at(cutout.flags, cutout.flag_bits, row, col),
        "target_x_frac": round(float(x_frac), 5),
        "target_y_frac": round(float(y_frac), 5),
        "quality": cutout.dqa,
        "astrometry_flag": cutout.astrometry_flag,
        "contamination": cutout.contamination,
        "psf_fwhm_arcsec": cutout.psf_fwhm_arcsec,
        "exposure_s": cutout.exposure_s,
        "processing_version": cutout.pipeline_version,
        "file_url": l2.s3_url(ref),
    }
    return _Frame(ref, clean, raw, bad_on_grid, noise, info)


def _stack_info(
    frames: list[_Frame], params: BlinkParams, grid: Grid, url: str, pass_index: int | None
) -> dict:
    """Dates, wavelength range and expected target place of a stack (at its mean date)."""
    mjds = [f.info["mjd"] for f in frames]
    lambdas = [f.info["lambda_um"] for f in frames]
    x_frac, y_frac = to_fraction(grid, *target_position(params, float(np.mean(mjds))))
    return {
        "pass_index": pass_index,  # None = every pass together
        "url": url,
        "n_images": len(frames),
        "mjd_start": min(mjds),
        "mjd_end": max(mjds),
        "date_start_utc": mjd_to_iso(min(mjds)),
        "date_end_utc": mjd_to_iso(max(mjds)),
        "lambda_min_um": min(lambdas),
        "lambda_max_um": max(lambdas),
        "target_x_frac": round(float(x_frac), 5),
        "target_y_frac": round(float(y_frac), 5),
    }


def run(params: BlinkParams, progress: Progress) -> dict[str, Any]:
    """The whole pipeline. Writes the files and returns the manifest (schemas.BlinkResult)."""
    s = get_settings()
    key = params.key()
    store = get_product_store()

    progress(0.02, "Searching SPHEREx images")
    images = sia.search(params.ra_deg, params.dec_deg)
    if not images:
        raise NoCoverage(
            "SPHEREx has no public images of this position yet.",
            detail={"ra_deg": params.ra_deg, "dec_deg": params.dec_deg, "collections": s.sia_collections},
        )
    available = [i for i in images if i.detector == params.detector]
    if not available:
        raise NoCoverage(
            f"Detector {params.detector} has no images of this position. Try another detector.",
            detail={"detectors_with_images": sorted({i.detector for i in images})},
        )
    refs = sia.select_frames(images, params.detector, params.max_frames)

    grid = make_grid(params.ra_deg, params.dec_deg, params.fov_arcmin)
    # The detector is rotated with respect to north: read the diagonal of the field, plus a margin.
    half_size_px = math.ceil(params.fov_arcmin * 60 / s.pixel_scale_arcsec / 2 * math.sqrt(2)) + 3
    frames, skipped = for_each_image(
        refs,
        lambda ref: _load_frame(ref, params, grid, half_size_px),
        progress,
        (0.05, 0.80),
        "Reading images",
    )
    frames.sort(key=lambda f: f.info["mjd"])
    if len(frames) < s.min_frames:
        raise NotEnoughFrames(
            f"Only {len(frames)} of {len(refs)} images could be used; at least {s.min_frames} are needed.",
            detail={"skipped": skipped},
        )

    progress(0.82, "Building the frames")
    folder = store.new_folder(KIND, key)
    # One brightness scale for every frame and stack: otherwise a change of scale looks like
    # a change in the sky.
    stretch = render.common_stretch([f.clean for f in frames], float(np.median([f.noise for f in frames])))
    for index, frame in enumerate(frames):
        # Flagged pixels are filled from the surrounding sky for display (not left as holes).
        picture = render.fill_hidden(frame.clean, frame.raw)
        render.save_frame(picture, stretch, folder / f"frame_{index:03d}.png")
        render.save_frame(frame.raw, stretch, folder / f"raw_{index:03d}.png")
        render.save_mask(frame.bad, folder / f"flags_{index:03d}.png")
        frame.info = {
            "index": index,
            "url": store.url(KIND, key, f"frame_{index:03d}.png"),
            "raw_url": store.url(KIND, key, f"raw_{index:03d}.png"),
            "flags_url": store.url(KIND, key, f"flags_{index:03d}.png"),
            **frame.info,
        }

    progress(0.90, "Stacking each survey pass")
    stacks, stack_data = [], {}
    for pass_index in sorted({f.ref.pass_index for f in frames}):
        members = [f for f in frames if f.ref.pass_index == pass_index]
        stack_data[pass_index] = stacking.stack([f.clean for f in members])
        name = f"stack_pass_{pass_index:02d}.png"
        render.save_frame(stack_data[pass_index], stretch, folder / name)
        stacks.append(_stack_info(members, params, grid, store.url(KIND, key, name), pass_index))
    render.save_frame(stacking.stack([f.clean for f in frames]), stretch, folder / "stack_all.png")
    stack_all = _stack_info(frames, params, grid, store.url(KIND, key, "stack_all.png"), None)

    # Each later pass minus the first one: what appeared, vanished or moved in between.
    differences = []
    first = min(stack_data)
    for pass_index in sorted(stack_data):
        if pass_index == first:
            continue
        name = f"difference_pass_{pass_index:02d}.png"
        limit = render.save_difference(
            stacking.difference(stack_data[pass_index], stack_data[first]), folder / name
        )
        differences.append(
            {
                "pass_index": pass_index,
                "reference_pass_index": first,
                "url": store.url(KIND, key, name),
                "limit_mjysr": round(limit, 5),
            }
        )

    progress(0.96, "Writing the animation")
    captions = [f"{f.info['date_utc'][:10]}  {f.info['lambda_um']:.3f} um  D{f.ref.detector}" for f in frames]
    pictures = [render.fill_hidden(f.clean, f.raw) for f in frames]
    render.save_gif(pictures, captions, stretch, folder / "blink.gif", s.gif_frame_ms)

    manifest = {
        "kind": KIND,
        "key": key,
        "params": asdict(params),
        "collections": s.sia_collections,
        "grid": grid.describe(),
        "stretch": stretch.describe(),
        "detector": params.detector,
        "n_available": len(available),
        "frames": [f.info for f in frames],
        "stacks": stacks,
        "stack_all": stack_all,
        "differences": differences,
        "gif_url": store.url(KIND, key, "blink.gif"),
        "skipped": skipped,
        "notes": NOTES,
    }
    # Written last: a folder with a manifest is a complete product.
    store.save_manifest(KIND, key, manifest)
    return manifest
