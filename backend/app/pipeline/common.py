"""What every pipeline needs when it works through a list of images.

One bad image must not sink a request: each image is tried `frame_tries` times, and if it still
fails it is skipped with a reason the user can read. The request fails only when too few are left.
"""

import datetime as dt
import logging
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from ..config import get_settings
from ..core.jobs import Job, Progress, finished_job, get_job_manager
from ..core.products import get_product_store
from ..data import l2
from ..data.sia import ImageRef

log = logging.getLogger(__name__)


def weekly_tag() -> str:
    """Part of every product key: results are recomputed each week, when new QR data arrives."""
    year, week, _ = dt.datetime.now(dt.UTC).isocalendar()
    return f"{year}W{week:02d}"


def mjd_to_iso(mjd: float) -> str:
    """UTC date and time of an MJD, to the second."""
    moment = dt.datetime(1858, 11, 17, tzinfo=dt.UTC) + dt.timedelta(days=mjd)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def read_cutout_with_retries(
    ref: ImageRef, ra_deg: float, dec_deg: float, half_size_px: int, **kwargs
) -> l2.Cutout:
    tries = get_settings().frame_tries
    last: Exception | None = None
    for attempt in range(1, tries + 1):
        try:
            return l2.read_cutout(ref, ra_deg, dec_deg, half_size_px, **kwargs)
        except l2.FrameSkipped:
            raise
        except Exception as e:  # noqa: BLE001 - network, S3 and FITS errors come in many types
            last = e
            log.warning(
                "image %s D%d: attempt %d/%d failed (%r)", ref.obs_id, ref.detector, attempt, tries, e
            )
            if attempt < tries:
                time.sleep(0.5 * attempt)
    raise l2.FrameSkipped(f"could not be read from the archive ({type(last).__name__})")


def for_each_image[T](
    refs: list[ImageRef],
    work: Callable[[ImageRef], T],
    progress: Progress,
    span: tuple[float, float],
    label: str,
) -> tuple[list[T], list[dict[str, Any]]]:
    """Run `work` on every image in parallel. Returns (results, skipped); progress moves inside `span`."""
    results: list[T] = []
    skipped: list[dict[str, Any]] = []
    start, end = span
    progress(start, f"{label} 0/{len(refs)}")
    with ThreadPoolExecutor(max_workers=get_settings().max_parallel_s3, thread_name_prefix="img") as pool:
        futures = {pool.submit(work, ref): ref for ref in refs}
        for done, future in enumerate(as_completed(futures), start=1):
            ref = futures[future]
            try:
                results.append(future.result())
            except l2.FrameSkipped as e:
                skipped.append({"obs_id": ref.obs_id, "detector": ref.detector, "reason": str(e)})
            except Exception as e:  # noqa: BLE001 - keep going with the other images
                log.exception("image %s D%d failed", ref.obs_id, ref.detector)
                skipped.append(
                    {
                        "obs_id": ref.obs_id,
                        "detector": ref.detector,
                        "reason": f"processing failed ({type(e).__name__})",
                    }
                )
            progress(start + (end - start) * done / len(refs), f"{label} {done}/{len(refs)}")
    return results, skipped


def start_job(kind: str, key: str, run: Callable[[Progress], dict[str, Any]]) -> Job:
    """Answer from disk when the product exists; otherwise queue the work (or join the running job)."""
    manifest = get_product_store().load_manifest(kind, key)
    if manifest is not None:
        return finished_job(key, kind, manifest)
    jobs = get_job_manager()
    jobs.forget_finished(key)  # its files are gone: compute again
    return jobs.submit(kind, key, run)
