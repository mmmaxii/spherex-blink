"""Photometry on synthetic cutouts whose true flux is known (no network: calibration maps are faked)."""

import math

import numpy as np
import pytest

from app.data import calibration
from app.data.l2 import FrameSkipped
from app.spectra import photometry
from tests.conftest import make_cutout, make_ref

RA, DEC = 150.0, 2.0
OMEGA_ARCSEC2 = 37.8
STAR_PEAK_MJYSR, STAR_SIGMA_PX = 5.0, 0.7  # the star painted by make_cutout


def true_flux_mjy(radius_px: float = 2.5) -> float:
    """Flux of make_cutout's Gaussian star inside the aperture, in mJy."""
    total = STAR_PEAK_MJYSR * 2 * math.pi * STAR_SIGMA_PX**2  # MJy/sr x pixel
    enclosed = 1 - math.exp(-(radius_px**2) / (2 * STAR_SIGMA_PX**2))
    return total * enclosed * OMEGA_ARCSEC2 * photometry.ARCSEC2_TO_SR * 1e9


@pytest.fixture
def fake_calibration(monkeypatch):
    monkeypatch.setattr(
        calibration, "at", lambda det, x, y: calibration.PixelCalibration(2.512, 0.071, OMEGA_ARCSEC2)
    )


def test_recovers_the_flux_of_a_clean_star(fake_calibration):
    m = photometry.measure(make_cutout(make_ref(1), RA, DEC))
    assert m.flux_mjy == pytest.approx(true_flux_mjy(), rel=0.02)
    assert m.lambda_um == 2.512 and m.lambda_source == "spectral_wcs"
    assert m.n_bad_px == 0 and m.lost_fraction == 0
    assert "SOURCE" in m.flags  # kept by the recipe, never a reason to drop the target
    assert m.flux_err_mjy > 0.03 * m.flux_mjy * 0.99  # includes the 3 % calibration term


def test_hot_pixel_in_the_sky_annulus_does_not_bias_the_sky(fake_calibration):
    with_hot = photometry.measure(make_cutout(make_ref(1), RA, DEC, hot_pixel=True))
    without = photometry.measure(make_cutout(make_ref(1), RA, DEC, hot_pixel=False))
    assert with_hot.background_mjysr == pytest.approx(without.background_mjysr, abs=0.01)


def test_flagged_pixel_inside_the_aperture_is_corrected(fake_calibration):
    cutout = make_cutout(make_ref(1), RA, DEC, hot_pixel=False)
    cutout.flags[30, 31] |= 1 << 2  # SUR_ERROR next to the star's centre
    cutout.image_mjysr[30, 31] = 500.0  # garbage value that must not leak into the flux
    m = photometry.measure(cutout)
    assert m.n_bad_px == 1 and 0 < m.lost_fraction < 0.2
    assert m.flux_mjy == pytest.approx(true_flux_mjy(), rel=0.05)


def test_saturated_core_is_skipped_with_a_reason(fake_calibration):
    cutout = make_cutout(make_ref(1), RA, DEC, hot_pixel=False)
    cutout.flags[29:32, 29:32] |= 1 << 2  # the whole core flagged, as on a saturated star
    with pytest.raises(FrameSkipped, match="flagged pixels"):
        photometry.measure(cutout)


def test_source_flag_everywhere_still_leaves_sky(fake_calibration):
    cutout = make_cutout(make_ref(1), RA, DEC, hot_pixel=False)
    cutout.flags |= 1 << 21  # DR1: SOURCE covers most of the field near bright stars
    m = photometry.measure(cutout)
    assert m.flux_mjy == pytest.approx(true_flux_mjy(), rel=0.02)


def test_falls_back_to_the_file_wavelength_without_calibration(monkeypatch):
    def unavailable(det, x, y):
        raise OSError("no network")

    monkeypatch.setattr(calibration, "at", unavailable)
    cutout = make_cutout(make_ref(1), RA, DEC)
    m = photometry.measure(cutout)
    assert m.lambda_source == "wcs-wave" and m.lambda_um == cutout.lambda_um


def test_target_at_the_edge_is_skipped(fake_calibration):
    cutout = make_cutout(make_ref(1), RA, DEC)
    cutout.x_px = 3.0
    with pytest.raises(FrameSkipped, match="edge"):
        photometry.measure(cutout)


def test_noise_only_gives_a_flux_compatible_with_zero(fake_calibration):
    cutout = make_cutout(make_ref(1), RA, DEC, hot_pixel=False)
    rng = np.random.default_rng(3)
    cutout.image_mjysr = (0.5 + rng.normal(0, 0.02, cutout.image_mjysr.shape)).astype(np.float32)
    m = photometry.measure(cutout)
    assert abs(m.flux_mjy) < 4 * m.stat_err_mjy


def _point(lam: float, flux: float, pass_index: int = 0) -> dict:
    return dict(
        lambda_um=lam, bandwidth_um=0.07, flux_mjy=flux, flux_err_mjy=0.03 * flux, pass_index=pass_index
    )


def test_cosmic_ray_within_a_pass_is_marked_suspect():
    from app.pipeline.spectrum import mark_suspects

    points = [_point(2.50, 10.0), _point(2.51, 10.3), _point(2.52, 9.8), _point(2.515, 60.0)]
    mark_suspects(points, factor=2.0)
    assert [p.get("suspect", False) for p in points] == [False, False, False, True]


def test_a_star_that_changes_between_passes_is_not_marked():
    from app.pipeline.spectrum import mark_suspects

    pass0 = [_point(2.50 + 0.01 * i, 10.0, pass_index=0) for i in range(4)]
    pass1 = [_point(2.50 + 0.01 * i, 25.0, pass_index=1) for i in range(4)]  # 2.5x brighter: real change
    mark_suspects(pass0 + pass1, factor=2.0)
    assert not any(p.get("suspect", False) for p in pass0 + pass1)


def test_a_saturated_target_gets_a_clear_sentence():
    from app.pipeline.spectrum import why_no_spectrum

    skipped = [{"reason": "95 % of the star's light falls on flagged pixels (BLOOM, SUR_ERROR)"}] * 9
    skipped.append({"reason": "position outside the detector"})
    text = why_no_spectrum(0, 10, skipped)
    assert "saturated" in text and "9 of 10" in text
    assert why_no_spectrum(1, 10, [{"reason": "position outside the detector"}] * 9).startswith(
        "Only 1 of 10"
    )
