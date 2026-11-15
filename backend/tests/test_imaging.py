"""Imaging: the common grid, alignment, stacking and rendering, on synthetic images."""

import numpy as np
from PIL import Image

from app.imaging import background, render
from app.imaging import stack as stacking
from app.imaging.align import align, align_mask
from app.imaging.grid import make_grid, to_fraction
from tests.conftest import make_cutout, make_ref

RA, DEC = 150.0, -30.0


def test_grid_is_north_up_east_left_and_centred():
    grid = make_grid(RA, DEC, 6.0)
    assert grid.shape[0] == grid.shape[1] == 117  # 6' at 6.15"/2 per pixel
    x, y = to_fraction(grid, RA, DEC)
    assert abs(x - 0.5) < 1e-6 and abs(y - 0.5) < 1e-6
    _, y_north = to_fraction(grid, RA, DEC + 1 / 60)
    x_east, _ = to_fraction(grid, RA + 1 / 60 / np.cos(np.radians(DEC)), DEC)
    assert y_north < 0.5  # north is towards the top of the picture
    assert x_east < 0.5  # east is to the left
    assert abs((0.5 - y_north) - 1 / 6) < 2e-3  # 1' is a sixth of a 6' field


def test_a_rotated_cutout_lands_where_the_sky_says():
    grid = make_grid(RA, DEC, 4.0)
    for rotation in (0.0, 30.0, 135.0):
        # star 5 native pixels along +x of the detector: its sky position depends on the rotation
        cutout = make_cutout(
            make_ref(0), RA, DEC, rotation_deg=rotation, star_offset_px=(5.0, 0.0), hot_pixel=False
        )
        sky = cutout.wcs.pixel_to_world_values(cutout.x_px + 5.0, cutout.y_px)
        aligned = align(cutout.image_mjysr - 0.5, cutout.wcs, grid)
        row, col = np.unravel_index(np.nanargmax(aligned), aligned.shape)
        x_frac, y_frac = to_fraction(grid, *sky)
        assert abs((col + 0.5) / grid.shape[1] - x_frac) < 1.5 / grid.shape[1]
        assert abs(1 - (row + 0.5) / grid.shape[0] - y_frac) < 1.5 / grid.shape[0]


def test_exact_and_interp_reprojection_agree_on_a_smooth_image():
    grid = make_grid(RA, DEC, 3.0)
    cutout = make_cutout(make_ref(0), RA, DEC, hot_pixel=False)
    a = align(cutout.image_mjysr, cutout.wcs, grid, "interp")
    b = align(cutout.image_mjysr, cutout.wcs, grid, "exact")
    both = np.isfinite(a) & np.isfinite(b)
    assert both.mean() > 0.95
    assert abs(np.median(a[both]) - np.median(b[both])) < 0.01


def test_mask_follows_the_image_onto_the_grid():
    grid = make_grid(RA, DEC, 4.0)
    cutout = make_cutout(make_ref(0), RA, DEC)
    bad = np.zeros(cutout.image_mjysr.shape, dtype=bool)
    bad[25, 33] = True  # inside the 4-arcmin field
    on_grid = align_mask(bad, cutout.wcs, grid)
    assert 1 <= on_grid.sum() <= 12  # one native pixel covers ~4 grid pixels


def test_background_ignores_flagged_pixels_and_stars():
    cutout = make_cutout(make_ref(0), RA, DEC)
    bad = np.zeros(cutout.image_mjysr.shape, dtype=bool)
    bad[24, 34] = True
    level, noise = background.estimate(cutout.image_mjysr, bad)
    assert abs(level - 0.5) < 0.01
    assert 0.015 < noise < 0.03


def test_stack_reduces_noise_and_rejects_an_outlier():
    rng = np.random.default_rng(1)
    frames = [rng.normal(0, 1, (40, 40)).astype(np.float32) for _ in range(16)]
    frames[3][20, 20] = 500.0  # a cosmic ray in one image
    frames[5][:, :5] = np.nan  # an image that does not cover one edge
    result = stacking.stack(frames)
    assert np.isfinite(result).all()
    assert abs(result[20, 20]) < 2.0
    assert 0.2 < np.std(result) < 0.35  # ~1/sqrt(16)
    assert np.isnan(stacking.stack([np.full((3, 3), np.nan, dtype=np.float32)] * 2)).all()


def test_frames_are_written_with_one_scale_and_transparent_gaps(tmp_path):
    faint = np.zeros((20, 20), dtype=np.float32)
    faint[5, 5] = 0.2  # 10 sigma
    bright = faint.copy()
    bright[5, 5] = 50.0
    bright[0, 0] = np.nan
    stretch = render.common_stretch([faint, bright], noise=0.02)
    assert stretch.vmin < 0 < stretch.vmax
    render.save_frame(faint, stretch, tmp_path / "a.png")
    render.save_frame(bright, stretch, tmp_path / "b.png")
    a, b = (np.asarray(Image.open(tmp_path / n)) for n in ("a.png", "b.png"))
    assert a.shape == (20, 20, 2)  # gray + alpha
    # arrays have south at row 0; the picture is flipped so north is up
    assert a[14, 5, 0] > a[0, 5, 0] + 40  # the 10-sigma source is clearly visible
    assert b[14, 5, 0] > a[14, 5, 0]  # and the brighter one is brighter on the same scale
    assert b[19, 0, 1] == 0 and b[10, 10, 1] == 255  # NaN is transparent


def test_difference_mask_and_gif_are_written(tmp_path):
    rng = np.random.default_rng(2)
    data = rng.normal(0, 0.05, (30, 30)).astype(np.float32)
    limit = render.save_difference(data, tmp_path / "d.png")
    assert 0.2 < limit < 0.4  # 6 sigma
    assert (
        abs(int(np.asarray(Image.open(tmp_path / "d.png"))[..., 0].mean()) - 128) < 12
    )  # mid-gray = no change

    mask = np.zeros((30, 30), dtype=bool)
    mask[0, 3] = True
    render.save_mask(mask, tmp_path / "m.png")
    rgba = np.asarray(Image.open(tmp_path / "m.png"))
    assert rgba[29, 3, 3] > 0 and rgba[..., 3].astype(bool).sum() == 1

    render.save_gif(
        [data, data + 0.1], ["one", "two"], render.common_stretch([data]), tmp_path / "g.gif", 500
    )
    gif = Image.open(tmp_path / "g.gif")
    assert gif.n_frames == 2


def test_fill_hidden_fills_flagged_pixels_but_not_missing_data():
    from app.imaging.render import fill_hidden

    raw = np.ones((40, 40), dtype=np.float32)
    raw[:, :5] = np.nan  # outside the detector: no data at all
    clean = raw.copy()
    clean[20, 20] = np.nan  # one flagged pixel
    clean[5:25, 10:30] = np.nan  # a big flagged core, wider than the smoothing kernel
    clean[20, 20] = np.nan
    picture = fill_hidden(clean, raw)
    assert np.isfinite(picture[5:25, 10:30]).all()  # every flagged pixel has a value now
    assert np.isnan(picture[:, :5]).all()  # "no data" stays transparent
    assert np.isfinite(clean[5:25, 10:30]).sum() == 0  # the input (used for measuring) is untouched


def test_relative_change_shows_only_the_star_that_changed(tmp_path):
    rng = np.random.default_rng(3)
    yy, xx = np.mgrid[:90, :90]

    def star(x, y, flux):
        return flux * np.exp(-((xx - x) ** 2 + (yy - y) ** 2) / (2 * 1.5**2))

    constant = sum(star(x, y, 5) for x in (15, 45, 75) for y in (15, 45, 75) if (x, y) != (45, 45))
    earlier = rng.normal(0, 0.01, (90, 90)) + constant + star(45, 45, 5)
    later = rng.normal(0, 0.01, (90, 90)) + constant + star(45, 45, 10)  # the middle one doubles
    change = stacking.relative_change(later.astype(np.float32), earlier.astype(np.float32))
    assert abs(change.relative[15, 15]) < change.threshold  # constant star: not coloured
    assert change.relative[45, 45] > 0.5  # 2x brighter: (10 - 5) / 7.5 = 0.67
    assert np.isnan(change.relative[30, 5])  # sky is not a star
    render.save_change(change.relative, change.has_data, change.threshold, tmp_path / "c.png")
    rgba = np.asarray(Image.open(tmp_path / "c.png"))[::-1]  # back to row 0 = south
    assert tuple(rgba[45, 45, :3]) == tuple(render.CHANGE_BRIGHTER)
    assert tuple(rgba[15, 15, :3]) == tuple(render.CHANGE_SAME)
    assert tuple(rgba[30, 5, :3]) == (0, 0, 0)
