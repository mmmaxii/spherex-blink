"""Build the small calibration grid the API ships with (app/data/calibration_dr1.npz).

The official per-pixel maps (spectral WCS: CWAVE, CBAND; solid angle per pixel) weigh ~50 MB per
detector, 300 MB for the six. Downloading them on the server filled most of the 512 MB of the
Render instance. They are smooth across the detector, so a grid of every 8th pixel, interpolated
bilinearly, is kept instead (~5 MB, loaded in memory).

Measured on the full DR1 maps (all pixels, all six detectors, 15 Nov 2026):
  - wavelength (CWAVE): within 0.04 % for 99 % of the pixels (a channel is ~2.5 % wide; WCS-WAVE
    differs from CWAVE by up to 0.13 %);
  - bandwidth (CBAND): within 1 % (median) and 5 % for 99 % of the pixels: CBAND has pixel-to-pixel
    noise of ~0.5 % that no grid follows. It only sets the "same wavelength" window (± half a band);
  - solid angle: within 2e-7, so fluxes in mJy do not change.

Run from backend/ (uses the maps in .cache/calibration when they are there, downloads them if not):
    python scripts/build_calibration_grid.py
"""

import sys
from pathlib import Path

import httpx
import numpy as np
from astropy.io import fits

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import get_settings  # noqa: E402
from app.data.calibration import GRID_FILE  # noqa: E402

STEP_PX = 8  # one knot every 8 pixels, plus the last pixel
DETECTORS = range(1, 7)


def local_or_download(key: str, folder: Path) -> Path:
    """The official file, from the local cache or from the public bucket."""
    path = folder / Path(key).name
    if not path.exists():
        print(f"downloading {key}")
        folder.mkdir(parents=True, exist_ok=True)
        response = httpx.get(get_settings().s3_https_base + key, timeout=300, follow_redirects=True)
        response.raise_for_status()
        path.write_bytes(response.content)
    return path


def knots_for(size_px: int) -> np.ndarray:
    """Pixel indices kept: 0, 8, 16, ... and the last pixel, so the grid covers the whole detector."""
    return np.unique(np.append(np.arange(0, size_px, STEP_PX), size_px - 1)).astype(np.int32)


def main() -> None:
    s = get_settings()
    folder = Path(s.cache_dir) / "calibration"
    lambdas, bands, omegas, knots = [], [], [], None
    for d in DETECTORS:
        swcs = local_or_download(s.spectral_wcs_key.format(d=d), folder)
        sapm = local_or_download(s.solid_angle_key.format(d=d), folder)
        cwave = fits.getdata(swcs, "CWAVE")
        cband = fits.getdata(swcs, "CBAND")
        omega = fits.getdata(sapm, "IMAGE")
        if knots is None:
            knots = knots_for(cwave.shape[0])
        pick = np.ix_(knots, knots)  # (row knots, column knots); the maps are square
        lambdas.append(np.asarray(cwave[pick], dtype=np.float32))
        bands.append(np.asarray(cband[pick], dtype=np.float32))
        omegas.append(np.asarray(omega[pick], dtype=np.float32))
        print(f"D{d}: {cwave.shape} -> {lambdas[-1].shape}")

    np.savez_compressed(
        GRID_FILE,
        knots_px=knots,
        lambda_um=np.stack(lambdas),
        bandwidth_um=np.stack(bands),
        solid_angle_arcsec2=np.stack(omegas),
        source=np.array([s.spectral_wcs_key, s.solid_angle_key]),
    )
    print(f"wrote {GRID_FILE} ({GRID_FILE.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
