"""Which SPHEREx images cover a position: one IRSA SIA2 query over every configured release.

SIA returns metadata only (date, detector, file location, footprint), ~2 s for ~450 images, so the
coverage of a position is known before reading any image. The query goes straight to the SIA URL
(CSV answer) instead of through astroquery, which adds a "capabilities" request that fails at times
(seen in 01_exploratory.ipynb). Selection logic ported from the blink notebook ("codiguin", cell 3).
"""

import csv
import io
import json
import logging
from dataclasses import asdict, dataclass, replace

import numpy as np

from ..config import get_settings
from ..core import cache
from ..core.http import fetch_text
from ..errors import UpstreamError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImageRef:
    """One L2 image (one detector, one exposure) as listed by SIA."""

    obs_id: str
    collection: str
    detector: int  # 1..6
    mjd: float  # middle of the exposure
    s3_key: str  # path inside the nasa-irsa-spherex bucket
    access_url: str  # same file at IRSA (cutout service, slower)
    lambda_min_um: float  # range of the whole detector, not of the position
    lambda_max_um: float
    pass_index: int = 0  # survey pass, 0 = first; filled by assign_passes


def _s3_key(row: dict[str, str]) -> str:
    try:
        return json.loads(row["cloud_access"])["aws"]["key"]
    except (KeyError, ValueError, TypeError):
        # VERIFY: fallback assumes the S3 key is the IRSA path without the "ibe/data/spherex/" prefix
        return row.get("access_url", "").split("ibe/data/spherex/", 1)[-1]


def parse_sia_csv(text: str) -> list[ImageRef]:
    """SIA2 CSV answer → images, one per (exposure, detector), sorted by date."""
    reader = csv.DictReader(io.StringIO(text))
    needed = {"obs_id", "energy_bandpassname", "t_min", "t_max", "access_url", "obs_collection"}
    if not reader.fieldnames or not needed.issubset(reader.fieldnames):
        raise UpstreamError(
            "IRSA answered in an unexpected format.",
            detail={"service": "irsa-sia", "start": text[:120]},
        )
    images: dict[tuple[str, int], ImageRef] = {}
    for row in reader:
        try:
            url = row["access_url"]
            if not url.endswith(".fits"):
                continue
            detector = int(row["energy_bandpassname"].rsplit("D", 1)[-1])  # "SPHEREx-D6" → 6
            image = ImageRef(
                obs_id=row["obs_id"],
                collection=row["obs_collection"],
                detector=detector,
                mjd=0.5 * (float(row["t_min"]) + float(row["t_max"])),
                s3_key=_s3_key(row),
                access_url=url,
                lambda_min_um=float(row.get("em_min") or "nan") * 1e6,
                lambda_max_um=float(row.get("em_max") or "nan") * 1e6,
            )
        except (KeyError, ValueError) as e:
            log.warning("skipping unreadable SIA row (%s)", e)
            continue
        images.setdefault((image.obs_id, image.detector), image)
    return assign_passes(sorted(images.values(), key=lambda i: i.mjd))


def assign_passes(images: list[ImageRef], gap_days: float | None = None) -> list[ImageRef]:
    """Number the survey passes: a new one starts after a gap longer than `pass_gap_days`.
    `images` must be sorted by date."""
    gap_days = gap_days if gap_days is not None else get_settings().pass_gap_days
    out, index = [], 0
    for i, image in enumerate(images):
        if i and image.mjd - images[i - 1].mjd > gap_days:
            index += 1
        out.append(replace(image, pass_index=index))
    return out


def search(ra_deg: float, dec_deg: float) -> list[ImageRef]:
    """Every image whose footprint contains the position, in all configured releases. Cached."""
    s = get_settings()
    key = cache.make_key("sia", ",".join(s.sia_collections), ra_deg, dec_deg, s.sia_radius_deg)
    rows = cache.get("sia", key, s.sia_cache_ttl_s)
    if rows is None:
        params = [("COLLECTION", c) for c in s.sia_collections]
        params += [
            ("POS", f"circle {ra_deg:.6f} {dec_deg:.6f} {s.sia_radius_deg}"),
            ("RESPONSEFORMAT", "CSV"),
        ]
        images = parse_sia_csv(fetch_text("irsa-sia", s.sia_url, params=params))
        cache.put("sia", key, [asdict(i) for i in images])
        return images
    return [ImageRef(**row) for row in rows]


def select_frames(images: list[ImageRef], detector: int, max_frames: int) -> list[ImageRef]:
    """Images of one detector, spread evenly in time inside each pass, at most `max_frames`.
    Every pass keeps at least two images when it has them, so passes can be compared."""
    candidates = [i for i in images if i.detector == detector]
    if len(candidates) <= max_frames:
        return candidates
    chosen: list[ImageRef] = []
    for index in sorted({i.pass_index for i in candidates}):
        in_pass = [i for i in candidates if i.pass_index == index]
        share = max(2, round(max_frames * len(in_pass) / len(candidates)))
        picks = np.unique(np.linspace(0, len(in_pass) - 1, min(share, len(in_pass)), dtype=int))
        chosen += [in_pass[k] for k in picks]
    return chosen


def summarize(images: list[ImageRef]) -> dict:
    """Coverage summary for the page: how many images, per detector and per survey pass."""
    detectors = []
    for detector in sorted({i.detector for i in images}):
        group = [i for i in images if i.detector == detector]
        detectors.append(
            {
                "detector": detector,
                "n_images": len(group),
                "lambda_min_um": round(group[0].lambda_min_um, 4),
                "lambda_max_um": round(group[0].lambda_max_um, 4),
            }
        )
    passes = []
    for index in sorted({i.pass_index for i in images}):
        group = [i for i in images if i.pass_index == index]
        passes.append(
            {
                "pass_index": index,
                "n_images": len(group),
                "mjd_start": group[0].mjd,
                "mjd_end": group[-1].mjd,
                "collections": sorted({i.collection for i in group}),
            }
        )
    return {"n_images": len(images), "detectors": detectors, "passes": passes}
