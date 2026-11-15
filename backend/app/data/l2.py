"""Reading a small piece of an L2 image straight from S3, without downloading the 65 MB file.

Only the bytes that are needed are asked for (HTTP Range), in 4 requests per image (6 with the
variance):
  1. the PRIMARY and IMAGE headers (the first ~58 KB);
  2. the rows of IMAGE around the position (float32, uncompressed, one row = NAXIS1 × 4 bytes);
  3. the FLAGS header and its row index (FLAGS is a RICE-compressed table, one row per tile);
  4. the compressed bytes of those rows, decoded here;
  5–6. (variance) the VARIANCE header and its rows.
The previous reader (astropy + fsspec) needed ~15 requests and ~3–10 MB per image; from Chile one
light curve of 240 images took 52 minutes. This layout and the decoding were checked against
astropy on real DR1 files (validation notebook maxi/04, and identical pixels in the comparison
run of 15 Nov 2026).

Rules that this module keeps:
- what the file says wins: data offsets, image size and flag names are read from its headers;
- the wavelength of the position comes from the per-pixel calibration maps (data/calibration.py);
  if they cannot be read, the middle of the detector's range is used and marked approximate;
- images whose astrometry failed (FINAST >= 2) are not used.

File layout (DR1): PRIMARY (VERSION), IMAGE [MJy/sr], FLAGS (compressed), VARIANCE, ZODI (not
subtracted from IMAGE), EPSF (441 zones; 451 in D3), WCS-WAVE.
"""

import logging
import threading
import warnings
from dataclasses import dataclass, field

import numpy as np
from astropy.io import fits
from astropy.io.fits.hdu.compressed._codecs import Rice1  # astropy's own RICE decoder (pinned)
from astropy.wcs import WCS, FITSFixedWarning

from ..config import get_settings
from ..core.http import fetch_range
from . import calibration
from . import flags as flaglib
from .sia import ImageRef

log = logging.getLogger(__name__)

# SPHEREx headers trigger harmless "fixed" notices in astropy; set once here because
# warnings.catch_warnings() is not safe across the threads that read images in parallel.
warnings.filterwarnings("ignore", category=FITSFixedWarning)

# wcslib parses headers with global state; building WCS objects one at a time keeps threads safe.
_WCS_LOCK = threading.Lock()

BLOCK = 2880  # FITS headers and data come in blocks of 2880 bytes
HEADER_READ_BYTES = 20 * BLOCK  # enough for every SPHEREx header; read more if not


class FrameSkipped(Exception):
    """This image cannot be used for this position; the reason is shown to the user."""


@dataclass
class Cutout:
    ref: ImageRef
    image_mjysr: np.ndarray  # float32 [MJy/sr], detector orientation, zodiacal light included
    wcs: WCS  # celestial WCS of the cutout (TAN-SIP)
    x_px: float  # position asked for, in cutout pixels (0-based)
    y_px: float
    detector_x_px: float  # same position in the full detector
    detector_y_px: float
    mjd: float
    lambda_um: float  # at the position
    bandwidth_um: float
    flags: np.ndarray | None = None
    flag_bits: dict[int, str] = field(default_factory=dict)
    variance: np.ndarray | None = None  # [(MJy/sr)^2]
    zodi_mjysr: np.ndarray | None = None
    psf_fwhm_arcsec: float | None = None
    dqa: str | None = None  # L2DQAFLG
    astrometry_flag: int | None = None  # FINAST: 0 good, 1 partial (corners off by ~2 px), >= 2 unusable
    pixel_solid_angle_arcsec2: float | None = None  # OMEGA_MEDIAN
    contamination: dict[str, bool] = field(default_factory=dict)  # *_CONT header keys
    exposure_s: float | None = None
    pipeline_version: str | None = None


def s3_url(ref: ImageRef) -> str:
    return get_settings().s3_https_base + ref.s3_key


def _padded(n_bytes: int) -> int:
    """Size on disk of a data unit: rounded up to whole 2880-byte blocks."""
    return -(-n_bytes // BLOCK) * BLOCK


def _bytes(url: str, start: int, stop: int) -> bytes:
    return fetch_range("s3-images", url, start, stop)


def _parse_header(raw: bytes, start: int) -> tuple[fits.Header, int] | None:
    """Header that begins at `raw[start]` and the offset right after it; None if `raw` ends first."""
    for block_start in range(start, len(raw) - BLOCK + 1, BLOCK):
        block = raw[block_start : block_start + BLOCK]
        for card in range(0, BLOCK, 80):
            if block[card : card + 3] == b"END" and not block[card + 3 : card + 80].strip():
                return fits.Header.fromstring(raw[start : block_start + BLOCK]), block_start + BLOCK
    return None


def _read_header(url: str, offset: int, extra: int = 0) -> tuple[fits.Header, int, bytes]:
    """Header at byte `offset` of the file → (header, offset of its data, the bytes read).
    `extra` bytes after the usual header size are read in the same request (e.g. a table)."""
    size = HEADER_READ_BYTES
    while True:
        raw = _bytes(url, offset, offset + size + extra)
        parsed = _parse_header(raw, 0)
        if parsed:
            header, length = parsed
            return header, offset + length, raw[length:]
        size *= 2  # rare: a longer header than usual


def _read_rows(url: str, data_start: int, n_cols: int, r0: int, r1: int, c0: int, c1: int) -> np.ndarray:
    """Rows r0..r1-1 of an uncompressed float32 image, columns c0..c1-1."""
    row_bytes = n_cols * 4
    raw = _bytes(url, data_start + r0 * row_bytes, data_start + r1 * row_bytes)
    rows = np.frombuffer(raw, dtype=">f4").reshape(r1 - r0, n_cols)
    return rows[:, c0:c1].astype(np.float32)


def _read_flags(url: str, header_start: int, r0: int, r1: int, c0: int, c1: int):
    """FLAGS rows r0..r1-1 → (flags, bit names, offset where the next extension starts).

    FLAGS is a binary table with one row per image row (ZTILE2 = 1); each row holds the size and
    the heap offset of that row's RICE-compressed bytes."""
    header, table_start, after = _read_header(url, header_start, extra=8 * 2048)
    n_rows, row_size = int(header["NAXIS2"]), int(header["NAXIS1"])  # one 8-byte descriptor per row
    table = after[: n_rows * row_size]
    if len(table) < n_rows * row_size:  # the extra bytes did not reach the end of the table
        table = _bytes(url, table_start, table_start + n_rows * row_size)
    descriptors = np.frombuffer(table, dtype=">i4").reshape(n_rows, 2)  # (n_bytes, heap offset)
    heap_start = table_start + int(header.get("THEAP", n_rows * row_size))

    wanted = descriptors[r0:r1]
    first, last = int(wanted[:, 1].min()), int((wanted[:, 1] + wanted[:, 0]).max())
    heap = _bytes(url, heap_start + first, heap_start + last)
    width = int(header["ZNAXIS1"])
    codec = Rice1(blocksize=int(header["ZVAL1"]), bytepix=int(header["ZVAL2"]), tilesize=width)
    rows = []
    for n_bytes, offset in wanted:
        compressed = np.frombuffer(heap[offset - first : offset - first + n_bytes], dtype=np.uint8)
        rows.append(np.asarray(codec.decode(compressed)).view("<i4")[:width])
    flags = np.stack(rows)[:, c0:c1]

    next_extension = table_start + _padded(n_rows * row_size + int(header.get("PCOUNT", 0)))
    return flags, flaglib.bit_names(header), next_extension


def _wavelength(ref: ImageRef, x: float, y: float) -> tuple[float, float]:
    """Wavelength and bandwidth at detector pixel (x, y), from the per-pixel calibration maps.
    Fallback (maps unavailable): the middle of the detector's range, a rough label only."""
    try:
        cal = calibration.at(ref.detector, x, y)
        return cal.lambda_um, cal.bandwidth_um
    except Exception:  # noqa: BLE001 - labels must not stop the images from being shown
        middle = (ref.lambda_min_um + ref.lambda_max_um) / 2
        return middle, middle / 40


def read_cutout(
    ref: ImageRef,
    ra_deg: float,
    dec_deg: float,
    half_size_px: int,
    *,
    with_flags: bool = True,
    with_variance: bool = False,
) -> Cutout:
    """Square piece of one image around a sky position (clipped at the detector edges)."""
    s = get_settings()
    url = s3_url(ref)

    # 1. Headers: what the image is, where its data starts, and where the position falls.
    head = _bytes(url, 0, HEADER_READ_BYTES)
    primary_and_end = _parse_header(head, 0)
    image_and_start = _parse_header(head, primary_and_end[1]) if primary_and_end else None
    if image_and_start is None:  # unusually long headers: read them one at a time
        primary, image_header_start, _ = _read_header(url, 0)
        header, data_start, _ = _read_header(url, image_header_start)
    else:
        primary = primary_and_end[0]
        header, data_start = image_and_start

    n_rows, n_cols = int(header["NAXIS2"]), int(header["NAXIS1"])
    finast = header.get("FINAST")
    if isinstance(finast, int) and finast > s.max_astrometry_flag:
        raise FrameSkipped(f"astrometry not reliable (FINAST = {finast})")
    with _WCS_LOCK:
        wcs = WCS(header)
        x, y = (float(v) for v in wcs.world_to_pixel_values(ra_deg, dec_deg))
    if not (np.isfinite(x) and np.isfinite(y) and 0 <= x < n_cols and 0 <= y < n_rows):
        raise FrameSkipped("position outside the detector")

    r0, r1 = max(0, round(y) - half_size_px), min(n_rows, round(y) + half_size_px + 1)
    c0, c1 = max(0, round(x) - half_size_px), min(n_cols, round(x) + half_size_px + 1)

    # 2. The rows of the image.
    image = _read_rows(url, data_start, n_cols, r0, r1, c0, c1)
    image_end = data_start + _padded(n_rows * n_cols * 4)
    lambda_um, bandwidth_um = _wavelength(ref, x, y)

    cutout = Cutout(
        ref=ref,
        image_mjysr=image,
        wcs=wcs[r0:r1, c0:c1],
        x_px=x - c0,
        y_px=y - r0,
        detector_x_px=x,
        detector_y_px=y,
        mjd=float(header.get("MJD-AVG", ref.mjd)),
        lambda_um=lambda_um,
        bandwidth_um=bandwidth_um,
        psf_fwhm_arcsec=_optional_float(header.get("PSF_FWHM")),
        dqa=str(header["L2DQAFLG"]) if "L2DQAFLG" in header else None,
        astrometry_flag=finast if isinstance(finast, int) else None,
        pixel_solid_angle_arcsec2=_optional_float(header.get("OMEGA_MEDIAN")),
        contamination={k: bool(v) for k, v in header.items() if k.endswith("_CONT")},
        exposure_s=_optional_float(header.get("XPOSURE")),
        pipeline_version=str(primary.get("VERSION", "")) or None,
    )

    # 3–4. Flags (also needed to find where VARIANCE starts).
    if with_flags or with_variance:
        flags, bits, flags_end = _read_flags(url, image_end, r0, r1, c0, c1)
        if with_flags:
            cutout.flags, cutout.flag_bits = flags, bits

        # 5–6. Variance: the extension right after FLAGS, same layout as IMAGE.
        if with_variance:
            variance_header, variance_start, _ = _read_header(url, flags_end)
            if variance_header.get("EXTNAME") != "VARIANCE":
                raise FrameSkipped(f"unexpected extension {variance_header.get('EXTNAME')} after FLAGS")
            cutout.variance = _read_rows(url, variance_start, n_cols, r0, r1, c0, c1)
    return cutout


def _optional_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
