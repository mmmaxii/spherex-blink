"""From arrays to what the browser shows: PNG frames with one common brightness scale, and a GIF.

Every frame of a request uses the same scale, so a change of brightness on screen is a change in
the data. Scale ported from 01_exploratory.ipynb (cell 10): percentile limits + asinh stretch.
Arrays have row 0 at the bottom (south); images are written with north up.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from astropy.convolution import Gaussian2DKernel, interpolate_replace_nans
from astropy.stats import mad_std
from PIL import Image, ImageDraw

NO_DATA_RGB = (23, 39, 71)  # same dark blue as the notebook for "no data"


@dataclass(frozen=True)
class Stretch:
    vmin: float
    vmax: float
    asinh_a: float = 0.1

    def apply(self, data: np.ndarray) -> np.ndarray:
        """Values → 0..1 (NaN stays NaN)."""
        x = np.clip((data - self.vmin) / (self.vmax - self.vmin), 0.0, 1.0)
        return np.arcsinh(x / self.asinh_a) / np.arcsinh(1.0 / self.asinh_a)

    def describe(self) -> dict:
        return {"kind": "asinh", "vmin_mjysr": self.vmin, "vmax_mjysr": self.vmax, "asinh_a": self.asinh_a}


def common_stretch(frames: list[np.ndarray], noise: float | None = None, high_pct: float = 99.9) -> Stretch:
    """One scale for a set of background-subtracted frames, tied to their noise so faint sources
    show: black at −2σ, sources a few σ above the sky already visible, bright stars not burnt out
    (asinh). `noise` is the typical per-image noise; estimated from the data when not given."""
    values = np.concatenate([f[np.isfinite(f)] for f in frames])
    if values.size == 0:
        return Stretch(0.0, 1.0)
    sigma = noise if noise and np.isfinite(noise) and noise > 0 else float(mad_std(values))
    if not sigma > 0:
        sigma = 1.0
    vmin = -2.0 * sigma
    vmax = max(float(np.percentile(values, high_pct)), vmin + 40.0 * sigma)
    return Stretch(vmin, vmax, asinh_a=float(np.clip(6.0 * sigma / (vmax - vmin), 1e-4, 1.0)))


def fill_hidden(clean: np.ndarray, raw: np.ndarray, smoothing_px: float = 2.0) -> np.ndarray:
    """Picture for display: hidden (flagged) pixels are filled from their surroundings, so the
    video shows sky instead of holes. Pixels without data in `raw` (outside the detector) stay NaN.

    Holes are filled by Gaussian interpolation of the valid neighbours; what is still empty after
    that (the core of a saturated star, wider than the kernel) gets 0, the sky level, because the
    frames are background-subtracted. Only for pictures: measurements never use filled pixels.
    """
    hidden = np.isnan(clean) & np.isfinite(raw)
    if not hidden.any():
        return clean
    filled = interpolate_replace_nans(clean, Gaussian2DKernel(x_stddev=smoothing_px))
    still_empty = hidden & ~np.isfinite(filled)
    filled[still_empty] = 0.0
    filled[~np.isfinite(raw)] = np.nan  # keep "no data" transparent
    return filled.astype(np.float32)


def _gray(data: np.ndarray, stretch: Stretch) -> tuple[np.ndarray, np.ndarray]:
    """(8-bit gray, has-data mask), flipped so north is up."""
    valid = np.isfinite(data)
    gray = (np.nan_to_num(stretch.apply(data)) * 255).round().astype(np.uint8)
    return gray[::-1], valid[::-1]


def save_frame(data: np.ndarray, stretch: Stretch, path: Path) -> None:
    """Gray PNG; pixels without data are transparent."""
    gray, valid = _gray(data, stretch)
    Image.merge("LA", [Image.fromarray(gray), Image.fromarray((valid * 255).astype(np.uint8))]).save(
        path, optimize=True
    )


def save_difference(data: np.ndarray, path: Path, n_sigma: float = 6.0) -> float:
    """Gray PNG centred on zero (mid-gray = no change). Returns the ± limit used [MJy/sr]."""
    finite = data[np.isfinite(data)]
    noise = float(mad_std(finite)) if finite.size else 0.0
    limit = n_sigma * noise if noise > 0 else 1.0
    save_frame(data, Stretch(-limit, limit, asinh_a=1e6), path)  # huge a = linear scale
    return limit


def save_values(data: np.ndarray, path: Path) -> None:
    """The aligned values themselves (MJy/sr, background removed), north up, as little-endian
    float16: the page adds or subtracts any set of frames chosen by the person. NaN = no data or a
    flagged pixel (never filled here: sums must not use invented values). ~27 KB for 117 x 117 px."""
    data[::-1].astype("<f2").tofile(path)


def save_mask(mask: np.ndarray, path: Path, rgba: tuple[int, int, int, int] = (255, 64, 64, 150)) -> None:
    """Transparent PNG with the masked pixels painted, to lay over a frame."""
    out = np.zeros((*mask.shape, 4), dtype=np.uint8)
    out[mask] = rgba
    Image.fromarray(out[::-1], "RGBA").save(path, optimize=True)


def save_gif(
    frames: list[np.ndarray],
    captions: list[str],
    stretch: Stretch,
    path: Path,
    frame_ms: int,
    size_px: int = 384,
) -> None:
    """Animated GIF of the frames with a caption (date and wavelength) under each one."""
    images = []
    for data, caption in zip(frames, captions, strict=True):
        gray, valid = _gray(data, stretch)
        rgb = np.repeat(gray[:, :, None], 3, axis=2)
        rgb[~valid] = NO_DATA_RGB
        picture = Image.fromarray(rgb, "RGB").resize((size_px, size_px), Image.NEAREST)
        canvas = Image.new("RGB", (size_px, size_px + 18), (0, 0, 0))
        canvas.paste(picture, (0, 0))
        ImageDraw.Draw(canvas).text((4, size_px + 3), caption, fill=(235, 235, 235))
        images.append(canvas)
    images[0].save(path, save_all=True, append_images=images[1:], duration=frame_ms, loop=0)
