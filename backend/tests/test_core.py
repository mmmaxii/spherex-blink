"""Plumbing: retries, cache, jobs and product files."""

import threading
import time

import httpx
import pytest

from app.core import cache, http
from app.core.jobs import JobManager
from app.core.products import ProductStore
from app.errors import Busy, NoCoverage, NotFound, UpstreamError, UpstreamTimeout


def _wait(job, timeout_s=5.0):
    deadline = time.time() + timeout_s
    while job.status in ("queued", "running") and time.time() < deadline:
        time.sleep(0.01)
    return job


# --- HTTP --------------------------------------------------------------------------------------


def _client_answering(monkeypatch, answers):
    """Replace the shared client by one that returns `answers` in order (status codes or exceptions)."""
    calls = []

    def handler(request):
        calls.append(request)
        answer = answers[min(len(calls), len(answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return httpx.Response(answer, text="ok")

    monkeypatch.setattr(http, "_client", httpx.Client(transport=httpx.MockTransport(handler)))
    return calls


def test_fetch_retries_after_a_503_and_then_succeeds(monkeypatch):
    calls = _client_answering(monkeypatch, [503, 503, 200])
    assert http.fetch_text("irsa-sia", "https://example.org/x") == "ok"
    assert len(calls) == 3


def test_fetch_gives_up_with_an_upstream_error(monkeypatch):
    calls = _client_answering(monkeypatch, [503])
    with pytest.raises(UpstreamError) as e:
        http.fetch_text("irsa-sia", "https://example.org/x", tries=3)
    assert len(calls) == 3 and e.value.detail["service"] == "irsa-sia"


def test_fetch_reports_timeouts_separately(monkeypatch):
    _client_answering(monkeypatch, [httpx.ReadTimeout("slow")])
    with pytest.raises(UpstreamTimeout):
        http.fetch_text("esa-gaia", "https://example.org/x", tries=2)


def test_fetch_does_not_retry_a_client_error(monkeypatch):
    calls = _client_answering(monkeypatch, [400])
    with pytest.raises(UpstreamError):
        http.fetch_text("irsa-sia", "https://example.org/x")
    assert len(calls) == 1


# --- cache -------------------------------------------------------------------------------------


def test_cache_computes_once_and_expires():
    key = cache.make_key("unit", 1.23456789, "x")
    assert key == cache.make_key("unit", 1.2345679, "x")  # floats are rounded to 6 decimals
    count = {"n": 0}

    def compute():
        count["n"] += 1
        return {"value": 42}

    assert cache.cached("unit", key, 60, compute) == {"value": 42}
    assert cache.cached("unit", key, 60, compute) == {"value": 42}
    assert count["n"] == 1
    assert cache.get("unit", key, ttl_s=-1) is None  # expired


# --- jobs --------------------------------------------------------------------------------------


def test_job_runs_reports_progress_and_keeps_its_result():
    jobs = JobManager(max_workers=1, max_queued=4, ttl_s=60)

    def work(progress):
        progress(0.5, "Halfway")
        return {"answer": 1}

    job = _wait(jobs.submit("blink", "abc12345", work))
    assert (job.status, job.progress, job.result) == ("done", 1.0, {"answer": 1})
    assert jobs.get("abc12345") is job
    jobs.shutdown()


def test_the_same_request_shares_one_job():
    jobs = JobManager(max_workers=1, max_queued=4, ttl_s=60)
    gate, runs = threading.Event(), []

    def work(progress):
        runs.append(1)
        gate.wait(2)
        return {}

    first = jobs.submit("blink", "same0001", work)
    second = jobs.submit("blink", "same0001", work)
    gate.set()
    _wait(first)
    assert first is second and len(runs) == 1
    jobs.shutdown()


def test_a_failed_job_keeps_the_error_and_can_be_started_again():
    jobs = JobManager(max_workers=1, max_queued=4, ttl_s=60)

    def no_images(progress):
        raise NoCoverage("Nothing here.")

    def crash(progress):
        raise ZeroDivisionError("secret detail")

    job = _wait(jobs.submit("blink", "fail0001", no_images))
    assert job.status == "failed" and job.error["code"] == "no_coverage"
    crashed = _wait(jobs.submit("blink", "fail0002", crash))
    assert crashed.error["code"] == "internal_error" and "secret" not in crashed.error["message"]
    again = _wait(jobs.submit("blink", "fail0001", lambda progress: {"ok": True}))
    assert again is not job and again.status == "done"
    jobs.shutdown()


def test_a_full_queue_answers_busy():
    jobs = JobManager(max_workers=1, max_queued=1, ttl_s=60)
    gate = threading.Event()
    jobs.submit("blink", "busy0001", lambda progress: gate.wait(2) or {})
    time.sleep(0.05)  # the first job is running; the next one waits in the queue
    jobs.submit("blink", "busy0002", lambda progress: {})
    with pytest.raises(Busy):
        jobs.submit("blink", "busy0003", lambda progress: {})
    gate.set()
    jobs.shutdown()


# --- products ----------------------------------------------------------------------------------


def test_products_are_stored_by_key_and_only_plain_names_are_served(tmp_path):
    store = ProductStore(tmp_path, max_products=2)
    folder = store.new_folder("blink", "aaaaaaaa01")
    (folder / "frame_000.png").write_bytes(b"png")
    assert store.load_manifest("blink", "aaaaaaaa01") is None  # not complete until the manifest exists
    store.save_manifest("blink", "aaaaaaaa01", {"kind": "blink"})
    assert store.load_manifest("blink", "aaaaaaaa01") == {"kind": "blink"}
    assert store.file("blink", "aaaaaaaa01", "frame_000.png").read_bytes() == b"png"
    for kind, key, name in [
        ("blink", "aaaaaaaa01", "../manifest.json"),
        ("blink", "../aaaaaaaa01", "frame_000.png"),
        ("..", "aaaaaaaa01", "frame_000.png"),
        ("blink", "aaaaaaaa01", "missing.png"),
        ("blink", "aaaaaaaa01", "frame_000.exe"),
    ]:
        with pytest.raises(NotFound):
            store.file(kind, key, name)


def test_old_products_are_removed_first(tmp_path):
    store = ProductStore(tmp_path, max_products=2)
    for i, key in enumerate(["aaaaaaaa01", "aaaaaaaa02", "aaaaaaaa03"]):
        store.new_folder("blink", key)
        time.sleep(0.02 * (i + 1))
        store.save_manifest("blink", key, {})
    assert store.load_manifest("blink", "aaaaaaaa01") is None
    assert store.load_manifest("blink", "aaaaaaaa03") == {}
