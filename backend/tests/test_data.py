"""Data layer: name and coordinate handling, SIA answers, flags. Uses saved real answers."""

import numpy as np
import pytest

from app.data import flags as flaglib
from app.data import calibration, resolve, sia
from app.errors import BadRequest, TargetNotFound, UpstreamError
from tests.conftest import FLAG_BITS, make_ref

# --- coordinates and names ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ra", "dec", "expected"),
    [
        ("133.795129", "-7.245147", (133.795129, -7.245147)),
        ("08h55m10.831s", "-7d14m42.53s", (133.795129, -7.245147)),  # WISE 0855, as in the challenge
        ("08 55 10.831", "-07 14 42.53", (133.795129, -7.245147)),
        ("08:55:10.831", "-07:14:42.53", (133.795129, -7.245147)),
        ("133.795129d", "-7.245147d", (133.795129, -7.245147)),
    ],
)
def test_coordinates_are_read_in_the_usual_formats(ra, dec, expected):
    ra_deg, dec_deg = resolve.parse_coordinates(ra, dec)
    assert ra_deg == pytest.approx(expected[0], abs=1e-5)
    assert dec_deg == pytest.approx(expected[1], abs=1e-5)


@pytest.mark.parametrize(("ra", "dec"), [("abc", "1"), ("10", "95"), ("400", "0"), ("", "")])
def test_unreadable_coordinates_are_a_bad_request(ra, dec):
    with pytest.raises(BadRequest):
        resolve.parse_coordinates(ra, dec)


def test_sesame_answer_gives_the_position_at_the_spherex_epoch(fixtures):
    target = resolve.parse_sesame(
        (fixtures / "sesame_eps_ind_b.xml").read_text(encoding="utf-8"), "eps Ind B"
    )
    assert target.name == "* eps Ind B"
    assert target.pm_ra_masyr == pytest.approx(3981.977)
    assert target.pm_dec_masyr == pytest.approx(-2466.832)
    assert target.catalog_ra_deg == pytest.approx(331.044147, abs=1e-6)
    # Same numbers as validation/notebooks/maxi/01_exploratory.ipynb (cell 1) for MJD 61050
    assert target.ra_deg == pytest.approx(331.09671858, abs=1e-6)
    assert target.dec_deg == pytest.approx(-56.80066604, abs=1e-6)


def test_unknown_name_is_reported_as_not_found(fixtures):
    with pytest.raises(TargetNotFound):
        resolve.parse_sesame((fixtures / "sesame_unknown.xml").read_text(encoding="utf-8"), "zzzz")


def test_linear_proper_motion_matches_astropy_over_the_survey():
    # eps Ind B from the reference epoch to 1.5 years later, against the catalogue propagation
    ra, dec = resolve.propagate(331.09671858, -56.80066604, 3981.977, -2466.832, 61050.0, 61050.0 + 365.25)
    assert (dec - -56.80066604) * 3600 == pytest.approx(-2.466832, abs=1e-4)
    assert (ra - 331.09671858) * 3600 * np.cos(np.radians(-56.8)) == pytest.approx(3.981977, abs=2e-3)


# --- SIA ---------------------------------------------------------------------------------------


def test_sia_answer_is_parsed_and_deduplicated(fixtures):
    images = sia.parse_sia_csv((fixtures / "sia_sample.csv").read_text(encoding="utf-8"))
    assert len(images) == 25  # the fixture has 26 rows, one repeated
    assert {i.collection for i in images} == {"spherex_dr1", "spherex_qr3"}
    assert {i.detector for i in images} == {1, 2, 3, 4, 5, 6}
    assert images == sorted(images, key=lambda i: i.mjd)
    first = images[0]
    assert first.s3_key.startswith("dr1/level2/") and first.s3_key.endswith(".fits")
    assert 0.7 < first.lambda_min_um < first.lambda_max_um < 5.1


def test_an_error_page_instead_of_csv_is_an_upstream_error():
    with pytest.raises(UpstreamError):
        sia.parse_sia_csv("<html><body>502 Proxy Error</body></html>")


def test_passes_split_on_long_gaps():
    images = [make_ref(i, mjd=m) for i, m in enumerate([60800, 60801, 60820, 60990, 60991, 61160])]
    assert [i.pass_index for i in sia.assign_passes(images, gap_days=30)] == [0, 0, 0, 1, 1, 2]


def test_selection_keeps_every_pass_and_respects_the_limit():
    mjds = [60800 + 0.1 * i for i in range(40)] + [60990 + 0.1 * i for i in range(4)]
    images = sia.assign_passes([make_ref(i, mjd=m) for i, m in enumerate(mjds)], gap_days=30)
    images += [make_ref(999, detector=2, mjd=60800.05)]
    chosen = sia.select_frames(images, detector=4, max_frames=12)
    assert all(i.detector == 4 for i in chosen)
    assert len(chosen) <= 14  # the limit, plus the minimum of two for small passes
    assert sum(i.pass_index == 1 for i in chosen) >= 2
    assert sia.select_frames(images, detector=4, max_frames=100) == [i for i in images if i.detector == 4]


# --- flags -------------------------------------------------------------------------------------


def test_flag_names_come_from_the_header_and_the_recipe_keeps_sources():
    header = {"MSKN0000": "TRANSIENT", "MSKN0010": "HOT", "MSKN0021": "SOURCE", "BITPIX": 32}
    bits = flaglib.bit_names(header)
    assert bits == {0: "TRANSIENT", 10: "HOT", 21: "SOURCE"}

    flags = np.zeros((4, 4), dtype=np.int32)
    flags[1, 1] = 1 << 21  # SOURCE only
    flags[2, 2] = (1 << 10) | (1 << 21)  # HOT + SOURCE
    flags[3, 3] = 1 << 0  # TRANSIENT only
    bad = flaglib.bad_mask(flags, bits)
    assert bad.sum() == 1 and bad[2, 2]
    assert flaglib.count_flags(flags, FLAG_BITS) == {"TRANSIENT": 1, "HOT": 1, "SOURCE": 2}
    assert flaglib.names_at(flags, FLAG_BITS, 2, 2) == ["HOT", "SOURCE"]
    assert flaglib.names_at(flags, FLAG_BITS, 99, 0) == []


def test_short_names_simbad_does_not_know_are_translated(monkeypatch, fixtures):
    asked = []

    def fetch_text(service, url, **kwargs):
        asked.append(url)
        return (fixtures / "sesame_eps_ind_b.xml").read_text(encoding="utf-8")

    monkeypatch.setattr(resolve, "fetch_text", fetch_text)
    resolve.from_name("WISE 0855-0714")
    assert asked[0].endswith("WISE%20J085510.83-071442.5")


def test_calibration_grid_gives_its_knots_exactly_and_stays_inside_the_band():
    g = calibration.grid()
    assert g.lambda_um.shape == (6, len(g.knots_px), len(g.knots_px))
    row, col = int(g.knots_px[10]), int(g.knots_px[20])
    on_knot = calibration.at(4, col, row)
    assert on_knot.lambda_um == float(g.lambda_um[3, 10, 20])
    between = calibration.at(4, col + 4, row + 4)  # middle of a grid cell
    corners = g.lambda_um[3, 10:12, 20:22]
    assert corners.min() <= between.lambda_um <= corners.max()
    assert 2.39 < between.lambda_um < 3.87  # detector 4 covers 2.4-3.9 um
    assert 37 < between.solid_angle_arcsec2 < 39  # ~6.15" pixels
    clipped = calibration.at(1, -5.0, 5000.0)  # positions off the detector use the nearest pixel
    assert clipped.lambda_um == calibration.at(1, 0, int(g.knots_px[-1])).lambda_um
