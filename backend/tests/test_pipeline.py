"""The blink pipeline from search to manifest, with the archive replaced by synthetic images."""

import numpy as np
import pytest
from PIL import Image

from app import schemas
from app.config import get_settings
from app.core.products import get_product_store
from app.data import l2, sia
from app.errors import NoCoverage, NotEnoughFrames
from app.pipeline import blink
from tests.conftest import make_cutout, make_ref

RA, DEC = 150.0, -30.0
PM_RA_MASYR = 8000.0  # a fast star: 8"/yr


def _fake_archive(monkeypatch, *, broken: set[int] = frozenset(), outside: set[int] = frozenset()):
    """Two survey passes 180 days apart, 4 images each, of a star that moves in RA."""
    refs = [make_ref(i, mjd=60800.0 + i) for i in range(4)] + [
        make_ref(10 + i, mjd=60980.0 + i) for i in range(4)
    ]
    refs = sia.assign_passes(refs, gap_days=30)
    monkeypatch.setattr(sia, "search", lambda ra, dec: refs)

    def read_cutout(ref, ra_deg, dec_deg, half_size_px, **kwargs):
        index = int(ref.obs_id.split("_")[1])
        if index in broken:
            raise OSError("connection reset")
        if index in outside:
            raise l2.FrameSkipped("position outside the detector")
        years = (ref.mjd - 60800.0) / 365.25
        shift_px = PM_RA_MASYR / 1000 * years / 6.15  # the star drifts east: -x on an unrotated detector
        return make_cutout(
            ref, ra_deg, dec_deg, rotation_deg=0.0, star_offset_px=(-shift_px, 0.0), seed=index
        )

    monkeypatch.setattr(l2, "read_cutout", read_cutout)
    return refs


def _params(**overrides):
    values = dict(ra_deg=RA, dec_deg=DEC, fov_arcmin=4.0, detector=4, max_frames=24,
                  pm_ra_masyr=PM_RA_MASYR, pm_dec_masyr=0.0, epoch_mjd=60800.0)  # fmt: skip
    return blink.BlinkParams(**{**values, **overrides})


def test_blink_produces_frames_stacks_differences_and_a_gif(monkeypatch):
    _fake_archive(monkeypatch)
    stages = []
    manifest = blink.run(_params(), lambda fraction, stage: stages.append((fraction, stage)))

    result = schemas.BlinkResult.model_validate(manifest)  # the manifest matches the published contract
    assert len(result.frames) == 8 and not result.skipped
    assert [f.pass_index for f in result.frames] == [0] * 4 + [1] * 4
    assert [s.n_images for s in result.stacks] == [4, 4] and result.stack_all.n_images == 8
    assert len(result.differences) == 1 and result.differences[0].reference_pass_index == 0
    assert [f for f, _ in stages] == sorted(f for f, _ in stages)  # progress never goes back
    assert stages[-1][0] < 1.0 and "Reading images 8/8" in [s for _, s in stages]

    store = get_product_store()
    frame = result.frames[0]
    urls = [frame.url, frame.raw_url, frame.flags_url, result.stacks[1].url, result.stack_all.url]
    for url in [*urls, result.differences[0].url, result.gif_url]:
        kind, key, name = url.split("/")[-3:]
        assert store.file(kind, key, name).stat().st_size > 0
    assert store.load_manifest("blink", result.key)["key"] == result.key


def test_the_marker_follows_the_star_and_the_star_is_under_it(monkeypatch):
    _fake_archive(monkeypatch)
    manifest = blink.run(_params(), lambda *_: None)
    first, last = manifest["frames"][0], manifest["frames"][-1]
    assert first["target_x_frac"] == pytest.approx(0.5, abs=1e-3)
    # half a year at 8"/yr = 4" east = left, on a 240" field
    assert first["target_x_frac"] - last["target_x_frac"] == pytest.approx(
        8.0 * (183 / 365.25) / 240, abs=2e-3
    )
    assert "SOURCE" in first["target_flags"]

    store = get_product_store()
    picture = np.asarray(Image.open(store.file("blink", manifest["key"], "frame_007.png")))[..., 0]
    row, col = np.unravel_index(picture.argmax(), picture.shape)
    assert (col + 0.5) / picture.shape[1] == pytest.approx(last["target_x_frac"], abs=0.02)
    assert (row + 0.5) / picture.shape[0] == pytest.approx(last["target_y_frac"], abs=0.02)


def test_flagged_pixels_are_filled_in_frames_but_kept_in_the_raw_version(monkeypatch):
    _fake_archive(monkeypatch)
    manifest = blink.run(_params(), lambda *_: None)
    store = get_product_store()
    clean, raw, flags = (
        np.asarray(Image.open(store.file("blink", manifest["key"], name)))
        for name in ("frame_000.png", "raw_000.png", "flags_000.png")
    )
    flagged = flags[..., 3] > 0
    assert flagged.sum() >= 1
    assert (clean[..., 1][flagged] == 255).all()  # filled from the surrounding sky, not a hole
    assert clean[..., 0][flagged].max() < 120  # ...and the hot pixel's value is gone
    assert (raw[..., 1][flagged] == 255).all() and raw[..., 0][flagged].max() == 255  # the hot pixel is there
    assert manifest["frames"][0]["flag_counts"]["HOT"] == 1
    stack = np.asarray(Image.open(store.file("blink", manifest["key"], "stack_pass_00.png")))
    assert stack[..., 0][flagged].max() < 120  # the hot pixel does not survive the stack


def test_unreadable_images_are_skipped_with_a_reason(monkeypatch):
    monkeypatch.setattr(get_settings(), "frame_tries", 2)
    monkeypatch.setattr("app.pipeline.common.time.sleep", lambda s: None)
    _fake_archive(monkeypatch, broken={1}, outside={12})
    manifest = blink.run(_params(), lambda *_: None)
    assert len(manifest["frames"]) == 6
    reasons = {s["obs_id"]: s["reason"] for s in manifest["skipped"]}
    assert "could not be read" in reasons["TEST_0001"] and "outside the detector" in reasons["TEST_0012"]


def test_too_few_usable_images_fails_with_the_reasons(monkeypatch):
    _fake_archive(monkeypatch, outside={0, 1, 2, 3, 10, 11, 12})
    with pytest.raises(NotEnoughFrames) as e:
        blink.run(_params(), lambda *_: None)
    assert len(e.value.detail["skipped"]) == 7


def test_no_images_or_no_images_of_the_detector_is_no_coverage(monkeypatch):
    _fake_archive(monkeypatch)
    with pytest.raises(NoCoverage) as e:
        blink.run(_params(detector=2), lambda *_: None)
    assert e.value.detail["detectors_with_images"] == [4]
    monkeypatch.setattr(sia, "search", lambda ra, dec: [])
    with pytest.raises(NoCoverage):
        blink.run(_params(), lambda *_: None)


def test_the_key_changes_with_the_request_and_not_otherwise():
    assert _params().key() == _params().key()
    assert _params().key() != _params(detector=5).key()
    assert _params().key() != _params(fov_arcmin=6.0).key()


def test_frames_come_with_their_values_for_adding_and_subtracting(monkeypatch):
    _fake_archive(monkeypatch)
    manifest = blink.run(_params(), lambda *_: None)
    frame = manifest["frames"][0]
    name = frame["data_url"].rsplit("/", 1)[-1]
    values = np.fromfile(get_product_store().file("blink", manifest["key"], name), dtype="<f2")
    grid = manifest["grid"]
    assert values.size == grid["width_px"] * grid["height_px"]
    picture = np.asarray(Image.open(get_product_store().file("blink", manifest["key"], "frame_000.png")))
    assert picture.shape[:2] == (grid["height_px"], grid["width_px"])  # same orientation and size
    assert np.isnan(values).any() and np.isfinite(values).sum() > 0.5 * values.size  # defects = NaN


def test_the_reference_pass_has_enough_images_to_remove_cosmic_rays():
    assert blink._reference_pass({0: 8, 1: 8}) == 0
    assert blink._reference_pass({0: 1, 1: 12, 2: 9}) == 1  # one image cannot be the reference
    assert blink._reference_pass({0: 2, 1: 1}) == 0  # none has 3: the one with most images
