"""Variability analysis on synthetic light curves and cutouts (no network)."""

import math

import numpy as np
import pytest

from app.data import calibration
from app.spectra import variability
from app.spectra.variability import StarPoint
from tests.conftest import make_cutout, make_ref

RNG = np.random.default_rng(7)


def spectrum(lam: float) -> float:
    """A smooth stellar spectrum: brightness changes with wavelength, as SPHEREx sees it."""
    return 20 + 10 * math.sin(lam)


def points_for(
    star: int, mjds: np.ndarray, factor_by_pass, noise: float, wings: bool = False
) -> list[StarPoint]:
    out = []
    for i, mjd in enumerate(mjds):
        lam = 0.8 + 4 * (i % 40) / 40  # each image at another wavelength; wavelengths repeat
        pass_index = int((mjd - mjds[0]) // 150)
        flux = spectrum(lam) * factor_by_pass(pass_index, mjd) * (1 + RNG.normal(0, noise))
        out.append(
            StarPoint(
                star=star,
                mjd=float(mjd),
                pass_index=pass_index,
                detector=1 + i % 6,
                lambda_um=lam,
                bandwidth_um=0.08,
                flux_mjy=None if wings else flux,
                snr=100.0,
                wing=flux if wings else None,
            )
        )
    return out


def three_passes() -> np.ndarray:
    return np.concatenate([np.linspace(0, 20, 80), np.linspace(180, 200, 80), np.linspace(360, 380, 80)])


def test_a_constant_star_is_not_called_variable():
    mjds = three_passes()
    points = points_for(0, mjds, lambda p, t: 1.0, 0.03)
    for star in range(1, 6):
        points += points_for(star, mjds, lambda p, t: 1.0, 0.03)
    result = variability.analyse(points)
    assert result["verdict"]["variable"] is False
    assert result["n_comparison_stars"] == 5
    assert all(abs(p["median"] - 1) < 0.03 for p in result["passes"])


def test_a_star_that_changes_between_passes_is_variable():
    mjds = three_passes()
    points = points_for(0, mjds, lambda p, t: [0.7, 1.0, 1.4][p], 0.03)
    for star in range(1, 6):
        points += points_for(star, mjds, lambda p, t: 1.0, 0.03)
    result = variability.analyse(points)
    assert result["verdict"]["variable"] is True
    medians = [p["median"] for p in result["passes"]]
    assert medians[0] < medians[1] < medians[2]


def test_wings_need_a_larger_change():
    """Saturated target measured on its wings: a 10 % scatter is within the method's limit."""
    mjds = three_passes()
    points = points_for(0, mjds, lambda p, t: 1.0, 0.10, wings=True)
    for star in range(1, 6):
        points += points_for(star, mjds, lambda p, t: 1.0, 0.02)
    result = variability.analyse(points)
    assert result["wing_share"] == 1.0
    assert result["verdict"]["variable"] is False and result["verdict"]["threshold"] >= 0.15
    assert "wings" in result["verdict"]["text"]


def test_period_is_found_with_continuous_sampling():
    t = np.arange(0, 520, 2.0)
    r = 1 + 0.3 * np.sin(2 * math.pi * t / 245) + RNG.normal(0, 0.03, len(t))
    found = variability.period_search(list(t), list(r))
    assert found["supported"] and found["period_d"] == pytest.approx(245, rel=0.05)


def test_period_is_refused_with_three_clumps():
    t = three_passes()
    r = 1 + 0.3 * np.sin(2 * math.pi * t / 10) + RNG.normal(0, 0.03, len(t))
    found = variability.period_search(list(t), list(r))
    assert found["supported"] is False


@pytest.fixture
def fake_calibration(monkeypatch):
    monkeypatch.setattr(calibration, "at", lambda det, x, y: calibration.PixelCalibration(2.5, 0.07, 37.8))


def test_measure_star_uses_the_aperture_or_the_wings(fake_calibration):
    cutout = make_cutout(make_ref(1), 150.0, 2.0, hot_pixel=False)
    clean = variability.measure_star(cutout, 0, cutout.x_px, cutout.y_px, with_wings=True)
    assert clean.flux_mjy is not None and clean.wing is not None
    cutout.flags[29:32, 29:32] |= 1 << 2  # saturated core: flagged
    saturated = variability.measure_star(cutout, 0, cutout.x_px, cutout.y_px, with_wings=True)
    assert saturated.flux_mjy is None and saturated.wing is not None
    assert variability.measure_star(cutout, 3, cutout.x_px, cutout.y_px, with_wings=False) is None


def test_repeated_detections_become_one_comparison_star():
    target = (150.0, 2.0)
    star = (150.0 + 60 / 3600, 2.0)  # 60" east of the target
    detections = [[(star[0] + 1e-5, star[1], 100.0)], [(star[0], star[1] - 1e-5, 90.0)], []]
    chosen = variability.choose_comparisons(detections, *target, max_radius_arcsec=400)
    assert len(chosen) == 1
