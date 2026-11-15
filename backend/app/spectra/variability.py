"""Does the target change brightness? Measured image by image and compared with stars of the same field.

Method validated on 15 Nov 2026 (validation/notebooks/maxi/04; prototype script 12):

  1. Each star (target and comparison stars) is measured on every image with the aperture of
     spectra/photometry.py. Each image sees a star at one wavelength, so a measurement is compared
     only with the same star at the same wavelength (±½ bandwidth) in the other images:
     residual = flux / median of those others. A constant star gives residuals around 1.
  2. Comparison stars (detected in the same cutouts, isolated, seen in most images) are the
     "constant star" reference: their scatter is what noise looks like at this place.
     Correcting each image by them was tested and not adopted: the real calibration error per
     image is only ~0.4–0.9 %, below the comparison noise, so the correction adds noise.
  3. Saturated targets: where the core of the star is flagged (more than 20 % of its light lost),
     the PSF wings are used instead: median of a 9–14 px ring outside the flagged core, minus the
     sky at 20–28 px. At one wavelength it is proportional to the star's flux, so its residuals
     follow the variability in relative units (R Dra: period 244.8 d, catalogue ~245 d).
     Limit, measured on Barnard's Star (quiet): wings scatter ~10 % and can fake ±20–30 % changes
     in the most saturated bands, so with wings only large changes are reported.
  4. Period: Lomb–Scargle on the residuals (outliers beyond 5 sigma removed), reported only when the
     sampling can support it (see `period_search`).

Validation results: eps Ind B scatter 3.8 % vs 4.0 % for comparison stars (constant), injected
10 % sinusoids recovered as 9.5 % with the right period; RW Aur 34 % vs 2.7 % (variable, brighter
in the blue and fainter at 4–5 µm between passes); R Dra 25 % vs 2.5 % with wings, P = 244.8 d.
"""

import math
from dataclasses import dataclass, replace

import numpy as np
import sep
from astropy.stats import sigma_clipped_stats
from astropy.timeseries import LombScargle

from ..config import get_settings
from ..data import calibration
from ..data.l2 import Cutout, FrameSkipped
from . import photometry

WING_INNER_PX, WING_OUTER_PX = 9.0, 14.0  # ring outside the flagged core of a saturated star
FAR_INNER_PX, FAR_OUTER_PX = 20.0, 28.0  # sky for the wing ring
DETECT_SIGMA = 10.0  # comparison stars: detections above this many sigma
MIN_COMPARISON_SNR = 20.0  # comparison stars used as the "constant" reference
WING_SYSTEMATIC = 0.15  # changes below this are not reported when the target is measured by its wings
APERTURE_FLOOR = 0.05  # smallest change recovered in the injection test (5 %)
SATURATED_SHARE = 0.3  # the target counts as saturated when its aperture fails on this share of images


# --- 1. Measuring one star on one image ----------------------------------------------------------


@dataclass(frozen=True)
class StarPoint:
    """One star on one image."""

    star: int  # 0 = target, 1.. = comparison stars
    mjd: float
    pass_index: int
    detector: int
    lambda_um: float
    bandwidth_um: float
    flux_mjy: float | None  # aperture flux, None when too much of the light is on flagged pixels
    snr: float | None
    wing: float | None  # PSF wing brightness, relative units (target only)


def wing_brightness(cutout: Cutout, x: float, y: float) -> float | None:
    """Median brightness of the PSF wings (9–14 px) minus the sky further out (20–28 px)."""
    image = cutout.image_mjysr.astype(np.float64)
    if not (FAR_OUTER_PX + 1 <= x < image.shape[1] - FAR_OUTER_PX - 1):
        return None
    if not (FAR_OUTER_PX + 1 <= y < image.shape[0] - FAR_OUTER_PX - 1):
        return None
    bad = photometry._bad_pixels(cutout, image)
    yy, xx = np.mgrid[: image.shape[0], : image.shape[1]]
    radius = np.hypot(xx - x, yy - y)
    wing = image[(radius >= WING_INNER_PX) & (radius < WING_OUTER_PX) & ~bad]
    far = image[(radius >= FAR_INNER_PX) & (radius < FAR_OUTER_PX) & ~bad]
    if len(wing) < 20 or len(far) < 30:
        return None
    _, sky, _ = sigma_clipped_stats(far, sigma=3.0)
    return float(np.median(wing) - sky)


def measure_star(cutout: Cutout, star: int, x: float, y: float, with_wings: bool) -> StarPoint | None:
    """Aperture flux (and, for the target, wing brightness) of a star at cutout pixel (x, y)."""
    image = cutout.image_mjysr.astype(np.float64)
    if not (0 <= x < image.shape[1] and 0 <= y < image.shape[0]):
        return None
    # The same image, measured at another place: move the "position asked for" there.
    shifted = replace(
        cutout,
        x_px=x,
        y_px=y,
        detector_x_px=cutout.detector_x_px + (x - cutout.x_px),
        detector_y_px=cutout.detector_y_px + (y - cutout.y_px),
    )
    flux = snr = None
    lambda_um, bandwidth_um = cutout.lambda_um, cutout.bandwidth_um
    try:
        m = photometry.measure(shifted)
        flux = m.flux_mjy
        snr = m.flux_mjy / m.stat_err_mjy if m.stat_err_mjy > 0 else None
        lambda_um, bandwidth_um = m.lambda_um, m.bandwidth_um
    except FrameSkipped:
        if not with_wings:
            return None
        try:  # the wavelength is still needed for the wing point
            cal = calibration.at(cutout.ref.detector, shifted.detector_x_px, shifted.detector_y_px)
            lambda_um, bandwidth_um = cal.lambda_um, cal.bandwidth_um
        except Exception:  # noqa: BLE001 - keep the file's own wavelength
            pass
    wing = wing_brightness(cutout, x, y) if with_wings else None
    if flux is None and wing is None:
        return None
    return StarPoint(
        star=star,
        mjd=cutout.mjd,
        pass_index=cutout.ref.pass_index,
        detector=cutout.ref.detector,
        lambda_um=lambda_um,
        bandwidth_um=bandwidth_um,
        flux_mjy=flux,
        snr=snr,
        wing=wing,
    )


# --- 2. Comparison stars -------------------------------------------------------------------------


def detect_sources(cutout: Cutout) -> list[tuple[float, float, float]]:
    """(ra_deg, dec_deg, flux) of stars detected in a cutout (sep, 10 sigma)."""
    image = np.ascontiguousarray(cutout.image_mjysr, dtype=np.float64)
    image = np.nan_to_num(image, nan=float(np.nanmedian(image)))
    background = sep.Background(image, bw=32, bh=32)
    found = sep.extract(image - background.back(), DETECT_SIGMA, err=background.globalrms, minarea=3)
    sources = []
    for obj in found:
        ra, dec = cutout.wcs.pixel_to_world_values(obj["x"], obj["y"])
        sources.append((float(ra), float(dec), float(obj["flux"])))
    return sources


def _separation_arcsec(ra1: float, dec1: float, ra2: float, dec2: float) -> float:
    dra = (ra1 - ra2) * math.cos(math.radians((dec1 + dec2) / 2))
    return math.hypot(dra, dec1 - dec2) * 3600


def choose_comparisons(
    detections: list[list[tuple[float, float, float]]],
    target_ra: float,
    target_dec: float,
    max_radius_arcsec: float,
    max_stars: int = 30,
) -> list[tuple[float, float]]:
    """Stars seen in at least half of the sample images, isolated (no neighbour within 30″), more
    than 25″ from the target and within `max_radius_arcsec`; brightest first."""
    everything = sorted((d for image in detections for d in image), key=lambda d: -d[2])
    groups: list[dict] = []
    for ra, dec, flux in everything:  # group repeated detections of the same star (within 5″)
        for g in groups:
            if _separation_arcsec(ra, dec, g["ra"], g["dec"]) < 5:
                g["n"] += 1
                break
        else:
            groups.append({"ra": ra, "dec": dec, "flux": flux, "n": 1})
    chosen = []
    for g in groups:
        distance = _separation_arcsec(g["ra"], g["dec"], target_ra, target_dec)
        crowded = any(
            0 < _separation_arcsec(g["ra"], g["dec"], h["ra"], h["dec"]) < 30 for h in groups if h is not g
        )
        if g["n"] >= len(detections) / 2 and 25 < distance < max_radius_arcsec and not crowded:
            chosen.append((g["ra"], g["dec"]))
    return chosen[:max_stars]


# --- 3. Analysis -----------------------------------------------------------------------------------


def robust_scatter(values: list[float]) -> float | None:
    """1.4826 × median absolute deviation: a standard deviation that ignores a few outliers."""
    a = np.asarray([v for v in values if v is not None and math.isfinite(v)])
    if len(a) < 3:
        return None
    return float(1.4826 * np.median(np.abs(a - np.median(a))))


def same_wavelength_residuals(points: list[StarPoint], value: str) -> list[float | None]:
    """For each point: its value / median of the same star at the same wavelength (±½ bandwidth)
    in the OTHER images. None when there are fewer than two such images or no value."""
    lam = np.array([p.lambda_um for p in points])
    vals = np.array([getattr(p, value) if getattr(p, value) is not None else np.nan for p in points])
    out: list[float | None] = []
    for i, p in enumerate(points):
        near = (np.abs(lam - lam[i]) < 0.5 * p.bandwidth_um) & np.isfinite(vals)
        near[i] = False  # leave-one-out
        if near.sum() < 2 or not np.isfinite(vals[i]):
            out.append(None)
            continue
        reference = float(np.median(vals[near]))
        out.append(float(vals[i] / reference) if reference > 0 else None)
    return out


def target_light_curve(points: list[StarPoint]) -> list[dict]:
    """Residuals of the target: from the aperture where it is usable, from the wings elsewhere.
    Each set is normalised against itself, so the different units cancel.

    Wings are used only for a saturated star (aperture lost on at least 30 % of the images). On a
    faint star an occasional failed aperture is a cosmic ray, and its wings are just sky noise."""
    by_aperture = same_wavelength_residuals(points, "flux_mjy")
    aperture_failed = sum(p.flux_mjy is None for p in points) / len(points) if points else 0.0
    if aperture_failed >= SATURATED_SHARE:
        by_wings = same_wavelength_residuals(points, "wing")
    else:
        by_wings = [None] * len(points)
    curve = []
    for p, a, w in zip(points, by_aperture, by_wings, strict=True):
        if a is not None:
            curve.append({"mjd": p.mjd, "residual": a, "method": "aperture"})
        elif w is not None:
            curve.append({"mjd": p.mjd, "residual": w, "method": "wings"})
        else:
            continue
        curve[-1].update(lambda_um=p.lambda_um, pass_index=p.pass_index, detector=p.detector)
    return curve


def period_search(mjd: list[float], residual: list[float]) -> dict | None:
    """Lomb–Scargle best period between 2 and 1000 days. Reported only when the data can support it:
    power ≥ 0.25, at least 1.5 cycles in the time span, and no gap longer than half a period
    (three clumps of images six months apart cannot fix a period of days)."""
    t, r = np.asarray(mjd), np.asarray(residual)
    keep = np.abs(r - np.median(r)) < 5 * (robust_scatter(list(r)) or np.inf)
    t, r = t[keep], r[keep]
    if len(t) < 20:
        return None
    frequency, power = LombScargle(t, r).autopower(minimum_frequency=1 / 1000, maximum_frequency=1 / 2)
    best = int(np.argmax(power))
    period_d = float(1 / frequency[best])
    span_d = float(t.max() - t.min())
    largest_gap_d = float(np.max(np.diff(np.sort(t)))) if len(t) > 1 else span_d
    supported = power[best] >= 0.25 and span_d >= 1.5 * period_d and largest_gap_d < 0.5 * period_d
    return {
        "period_d": period_d,
        "power": float(power[best]),
        "span_d": span_d,
        "largest_gap_d": largest_gap_d,
        "supported": bool(supported),
    }


def bands_by_pass(curve: list[dict]) -> list[dict]:
    """Median residual of each SPHEREx band in each survey pass: shows whether a change depends on
    wavelength (a colour change) or not."""
    bands = [(0.75, 1.10), (1.10, 1.65), (1.65, 2.40), (2.40, 3.80), (3.80, 5.00)]
    rows = []
    for low, high in bands:
        cells = {}
        for p in sorted({c["pass_index"] for c in curve}):
            values = [c["residual"] for c in curve if c["pass_index"] == p and low <= c["lambda_um"] < high]
            if len(values) >= 3:
                cells[str(p)] = {"median": float(np.median(values)), "n": len(values)}
        rows.append({"lambda_min_um": low, "lambda_max_um": high, "passes": cells})
    return rows


def verdict(target_scatter: float | None, reference_scatter: float | None, wing_share: float) -> dict:
    """Plain-language conclusion and the threshold it used."""
    floor = WING_SYSTEMATIC if wing_share > 0.5 else APERTURE_FLOOR
    threshold = max(3 * (reference_scatter or 0.0), floor)
    if target_scatter is None:
        return {"variable": None, "threshold": threshold, "text": "Too few measurements to decide."}
    if target_scatter > threshold:
        text = (
            f"Varies: its brightness scatters {100 * target_scatter:.0f} % at the same wavelength, "
            f"against {100 * (reference_scatter or 0):.1f} % for constant stars of the same images."
        )
        return {"variable": True, "threshold": threshold, "text": text}
    text = (
        f"No change detected above {100 * threshold:.0f} % (scatter {100 * target_scatter:.1f} %, "
        f"constant stars {100 * (reference_scatter or 0):.1f} %)."
    )
    if wing_share > 0.5:
        text += " The star is saturated and was measured by its wings, which cannot see smaller changes."
    return {"variable": False, "threshold": threshold, "text": text}


def analyse(points: list[StarPoint]) -> dict:
    """Everything the page shows: light curve, reference scatter, passes, bands, period, verdict."""
    target = sorted((p for p in points if p.star == 0), key=lambda p: p.mjd)
    curve = target_light_curve(target)
    comparison_scatters, reference_cloud = [], []
    for star in sorted({p.star for p in points if p.star > 0}):
        own = sorted((p for p in points if p.star == star), key=lambda p: p.mjd)
        residuals = same_wavelength_residuals(own, "flux_mjy")
        bright = [
            r
            for p, r in zip(own, residuals, strict=True)
            if r is not None and (p.snr or 0) > MIN_COMPARISON_SNR
        ]
        scatter = robust_scatter(bright)
        if scatter is not None:
            comparison_scatters.append(scatter)
            reference_cloud += [
                {"mjd": p.mjd, "residual": r}
                for p, r in zip(own, residuals, strict=True)
                if r is not None and (p.snr or 0) > MIN_COMPARISON_SNR
            ]
    reference_scatter = float(np.median(comparison_scatters)) if comparison_scatters else None
    target_scatter = robust_scatter([c["residual"] for c in curve])
    wing_share = sum(c["method"] == "wings" for c in curve) / len(curve) if curve else 0.0

    passes = []
    for p in sorted({c["pass_index"] for c in curve}):
        values = [c["residual"] for c in curve if c["pass_index"] == p]
        scatter = robust_scatter(values)
        passes.append(
            {
                "pass_index": p,
                "n": len(values),
                "median": float(np.median(values)),
                "error": (1.25 * scatter / math.sqrt(len(values))) if scatter else None,
                "mjd_start": min(c["mjd"] for c in curve if c["pass_index"] == p),
                "mjd_end": max(c["mjd"] for c in curve if c["pass_index"] == p),
            }
        )

    period = period_search([c["mjd"] for c in curve], [c["residual"] for c in curve]) if curve else None
    if period and reference_cloud:  # the same search on the constant stars: should find nothing
        null = period_search([c["mjd"] for c in reference_cloud], [c["residual"] for c in reference_cloud])
        period["reference_power"] = null["power"] if null else None
        if null and null["power"] >= 0.1:
            period["supported"] = False

    # Keep the reference cloud small for the page (it can have thousands of points).
    step = max(1, len(reference_cloud) // 1500)
    return {
        "light_curve": curve,
        "reference": reference_cloud[::step],
        "n_comparison_stars": len(comparison_scatters),
        "target_scatter": target_scatter,
        "reference_scatter": reference_scatter,
        "wing_share": wing_share,
        "passes": passes,
        "bands": bands_by_pass(curve),
        "period": period,
        "verdict": verdict(target_scatter, reference_scatter, wing_share),
    }


def settings_summary() -> dict:
    """Numbers quoted on the page, so text and code cannot drift apart."""
    s = get_settings()
    return {
        "aperture_radius_px": s.aperture_radius_px,
        "wing_ring_px": [WING_INNER_PX, WING_OUTER_PX],
        "wing_systematic": WING_SYSTEMATIC,
        "aperture_floor": APERTURE_FLOOR,
    }
