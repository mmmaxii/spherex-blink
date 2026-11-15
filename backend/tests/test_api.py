"""The HTTP contract: shapes, error format and the job flow, without internet."""

import time

import pytest
from fastapi.testclient import TestClient

from app.data import calibration, catalogs, l2, sia
from app.main import app
from tests.conftest import make_cutout, make_ref

client = TestClient(app)
WHERE = {"ra_deg": 150.0, "dec_deg": -30.0}


def _archive(monkeypatch):
    refs = sia.assign_passes(
        [make_ref(i, mjd=60800.0 + i) for i in range(3)]
        + [make_ref(10 + i, mjd=60980.0 + i) for i in range(3)],
        gap_days=30,
    )
    monkeypatch.setattr(sia, "search", lambda ra, dec: refs)
    monkeypatch.setattr(
        l2, "read_cutout", lambda ref, ra, dec, half, **kw: make_cutout(ref, ra, dec, seed=int(ref.mjd))
    )


def _poll(job: dict, timeout_s: float = 30.0) -> dict:
    deadline = time.time() + timeout_s
    while job["status"] in ("queued", "running") and time.time() < deadline:
        time.sleep(0.05)
        job = client.get(f"/api/jobs/{job['job_id']}").json()
    return job


def test_health_reports_releases_and_what_is_ready():
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["collections"] == ["spherex_dr1", "spherex_qr3"]
    assert body["spectrum_ready"] is True and body["classifier_ready"] is False
    assert set(body["jobs"]) == {"queued", "running", "done", "failed"}


def test_openapi_schema_lists_the_contract():
    schema = client.get("/openapi.json").json()
    for name in ["health", "resolve", "coverage", "frames", "spectrum", "overlay", "jobs/{job_id}"]:
        assert f"/api/{name}" in schema["paths"]
    for model in ["BlinkResult", "FrameInfo", "SpectrumResult", "JobStatus", "ErrorResponse"]:
        assert model in schema["components"]["schemas"]


def test_every_error_has_the_same_shape():
    invalid = client.get("/api/frames", params={"ra_deg": 400, "dec_deg": 0, "detector": 9})
    assert invalid.status_code == 422
    error = invalid.json()["error"]
    assert error["code"] == "invalid_parameters" and "ra_deg" in error["message"] and error["request_id"]

    for response, status, code in [
        (client.get("/api/resolve"), 400, "bad_request"),
        (client.get("/api/resolve", params={"ra": "abc", "dec": "1"}), 400, "bad_request"),
        (client.get("/api/frames", params={**WHERE, "detector": 4, "fov_arcmin": 90}), 400, "bad_request"),
        (client.get("/api/jobs/doesnotexist"), 404, "not_found"),
        (client.get("/api/products/blink/aaaaaaaa01/frame_000.png"), 404, "not_found"),
        (client.get("/api/nothing-here"), 404, "not_found"),
    ]:
        assert response.status_code == status, response.text
        assert response.json()["error"]["code"] == code
        assert response.headers["X-Request-ID"]


def test_resolve_reads_typed_coordinates():
    body = client.get("/api/resolve", params={"ra": "08h55m10.831s", "dec": "-7d14m42.53s"}).json()
    assert body["source"] == "coordinates"
    assert body["ra_deg"] == pytest.approx(133.795129, abs=1e-5)
    assert body["pm_ra_masyr"] is None


def test_coverage_summarises_detectors_and_passes(monkeypatch):
    _archive(monkeypatch)
    body = client.get("/api/coverage", params=WHERE).json()
    assert body["n_images"] == 6
    assert body["detectors"] == [{"detector": 4, "n_images": 6, "lambda_min_um": 2.4, "lambda_max_um": 3.8}]
    assert [p["n_images"] for p in body["passes"]] == [3, 3]
    assert body["passes"][0]["date_start_utc"].startswith("2025-05-05")

    monkeypatch.setattr(sia, "search", lambda ra, dec: [])
    empty = client.get("/api/coverage", params=WHERE)
    assert empty.status_code == 404 and empty.json()["error"]["code"] == "no_coverage"


def test_frames_job_runs_to_a_result_and_is_served_from_disk_afterwards(monkeypatch):
    _archive(monkeypatch)
    params = {**WHERE, "detector": 4, "fov_arcmin": 3}
    started = client.get("/api/frames", params=params)
    assert started.status_code == 200
    job = _poll(started.json())
    assert job["status"] == "done", job
    result = job["result"]
    assert result["kind"] == "blink" and len(result["frames"]) == 6 and len(result["stacks"]) == 2

    picture = client.get(result["frames"][0]["url"])
    assert picture.status_code == 200 and picture.headers["content-type"] == "image/png"
    assert "immutable" in picture.headers["cache-control"]
    assert client.get(result["gif_url"]).headers["content-type"] == "image/gif"

    again = client.get("/api/frames", params=params).json()
    assert again["status"] == "done" and again["job_id"] == job["job_id"]


def test_a_failed_job_carries_the_error(monkeypatch):
    _archive(monkeypatch)
    job = _poll(client.get("/api/frames", params={**WHERE, "detector": 2}).json())
    assert job["status"] == "failed"
    assert job["error"]["code"] == "no_coverage" and job["error"]["detail"]["detectors_with_images"] == [4]


def test_cube_spectrum_is_not_built_yet():
    response = client.get("/api/spectrum", params={**WHERE, "mode": "cube"})
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_implemented"


def test_spectrum_job_returns_one_point_per_image(monkeypatch):
    _archive(monkeypatch)
    fake = calibration.PixelCalibration(lambda_um=2.5, bandwidth_um=0.07, solid_angle_arcsec2=37.8)
    monkeypatch.setattr(calibration, "at", lambda det, x, y: fake)
    job = _poll(client.get("/api/spectrum", params={**WHERE, "mode": "pass"}).json())
    assert job["status"] == "done", job.get("error")
    result = job["result"]
    assert len(result["points"]) == 6 and [p["n_points"] for p in result["passes"]] == [3, 3]
    point = result["points"][0]
    assert point["lambda_source"] == "spectral_wcs" and point["flux_mjy"] > 0
    assert point["flux_err_mjy"] >= 0.03 * point["flux_mjy"] and point["suspect"] is False


def test_overlay_places_catalogue_sources_on_the_frame(monkeypatch):
    def cone(catalog, ra_deg, dec_deg, radius_deg):
        fixed = {"pm_ra_masyr": None, "pm_dec_masyr": None, "epoch_jyear": 2016.0, "band": "G"}
        return [
            {**fixed, "id": "centre", "ra_deg": ra_deg, "dec_deg": dec_deg, "mag": 12.0},
            {**fixed, "id": "north", "ra_deg": ra_deg, "dec_deg": dec_deg + 1 / 60, "mag": 14.0,
             "pm_ra_masyr": 0.0, "pm_dec_masyr": 0.0},
            {**fixed, "id": "outside", "ra_deg": ra_deg, "dec_deg": dec_deg + 0.2, "mag": 9.0},
        ]  # fmt: skip

    monkeypatch.setattr(catalogs, "cone", cone)
    body = client.get("/api/overlay", params={**WHERE, "fov_arcmin": 6, "catalog": "gaia"}).json()
    by_id = {s["id"]: s for s in body["sources"]}
    assert set(by_id) == {"centre", "north"}
    assert by_id["centre"]["x_frac"] == pytest.approx(0.5, abs=1e-3)
    assert by_id["north"]["y_frac"] == pytest.approx(0.5 - 1 / 6, abs=2e-3)
