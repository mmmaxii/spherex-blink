from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_reports_current_collections():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["collections"] == ["spherex_dr1", "spherex_qr3"]


def test_unbuilt_endpoints_answer_501():
    r = client.get("/api/coverage", params={"ra_deg": 133.76, "dec_deg": -7.2422})
    assert r.status_code == 501


def test_openapi_schema_lists_the_contract():
    paths = client.get("/openapi.json").json()["paths"]
    expected = ["health", "resolve", "coverage", "frames", "difference", "spectrum"]
    for p in (f"/api/{name}" for name in expected):
        assert p in paths
