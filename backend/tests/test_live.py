"""Checks against the real services. Not part of the normal run: `pytest -m live` (about a minute)."""

import pytest

from app.data import catalogs, resolve, sia
from app.pipeline import blink

pytestmark = pytest.mark.live


def test_wise_0855_is_resolved_and_covered():
    target = resolve.from_name("WISE 0855-0714")
    assert target.pm_ra_masyr is not None and abs(target.pm_ra_masyr) > 5000  # ~8"/yr
    images = sia.search(target.ra_deg, target.dec_deg)
    assert len(images) > 100
    assert {i.collection for i in images} <= {"spherex_dr1", "spherex_qr3"}


def test_blink_of_eps_ind_b_from_the_archive():
    target = resolve.from_name("eps Ind B")
    params = blink.BlinkParams(
        target.ra_deg, target.dec_deg, 4.0, 4, 6, target.pm_ra_masyr, target.pm_dec_masyr, target.epoch_mjd
    )
    manifest = blink.run(params, lambda *_: None)
    assert len(manifest["frames"]) >= 4
    assert all(2.3 < f["lambda_um"] < 3.9 for f in manifest["frames"])  # detector 4


@pytest.mark.parametrize("catalog", catalogs.CATALOGS)
def test_overlay_catalogues_answer(catalog):
    sources = catalogs.cone(catalog, 331.0967, -56.8007, 0.07)
    assert len(sources) > 5 and all(-90 <= s["dec_deg"] <= 90 for s in sources)
