"""One HTTP client for every external service, with retries, timeouts and a per-service limit.

    text = fetch_text("irsa-sia", settings.sia_url, params={...})

Retries cover network errors and 429/5xx answers (IRSA returns 503 under load: seen in the
notebooks). After the last attempt the caller gets UpstreamError / UpstreamTimeout, which the API
reports as 502 / 504 with the service name.
"""

import logging
import random
import threading
import time
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from ..config import get_settings
from ..errors import UpstreamError, UpstreamTimeout

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}

# How each service is called in the sentences people read (logs keep the short names).
SERVICE_NAMES = {
    "irsa-sia": "The NASA/IPAC archive (IRSA) image search",
    "irsa-scs": "The IRSA catalogue service",
    "cds-sesame": "The CDS name resolver (Sesame)",
    "esa-gaia": "The ESA Gaia archive",
    "s3-images": "The SPHEREx image store (AWS S3)",
}

_client: httpx.Client | None = None
_client_lock = threading.Lock()
_limits: dict[str, threading.BoundedSemaphore] = {}


def get_client() -> httpx.Client:
    global _client
    with _client_lock:
        if _client is None:
            s = get_settings()
            _client = httpx.Client(
                timeout=httpx.Timeout(s.http_timeout_s, connect=10.0),
                follow_redirects=True,  # Sesame redirects to a mirror when Strasbourg is down
                headers={"User-Agent": "spherex-blink"},
            )
        return _client


def close_client() -> None:
    global _client
    with _client_lock:
        if _client is not None:
            _client.close()
            _client = None


def _limit_for(service: str) -> threading.BoundedSemaphore:
    """IRSA services share one limit; every other service gets its own."""
    group = "irsa" if service.startswith("irsa") else service
    with _client_lock:
        if group not in _limits:
            _limits[group] = threading.BoundedSemaphore(get_settings().max_parallel_irsa)
        return _limits[group]


Params = Mapping[str, Any] | Sequence[tuple[str, Any]]


def fetch(
    service: str,
    url: str,
    *,
    params: Params | None = None,
    tries: int | None = None,
    headers: Mapping[str, str] | None = None,
) -> httpx.Response:
    """GET with retries. `service` is a short name used in logs and error messages; `headers`
    is used for byte ranges of S3 files (Range: bytes=start-end)."""
    s = get_settings()
    tries = tries or s.http_tries
    last: Exception | None = None
    timed_out = False
    for attempt in range(1, tries + 1):
        try:
            with _limit_for(service):
                response = get_client().get(url, params=params, headers=headers)
            if response.status_code not in RETRY_STATUS:
                if response.status_code >= 400:
                    raise UpstreamError(
                        f"{service} answered {response.status_code}.",
                        detail={"service": service, "status": response.status_code},
                    )
                return response
            last = UpstreamError(f"{service} answered {response.status_code}.")
            timed_out = False
        except httpx.TimeoutException as e:
            last, timed_out = e, True
        except httpx.TransportError as e:
            last, timed_out = e, False
        if attempt < tries:
            wait_s = min(s.http_backoff_s * 2 ** (attempt - 1), s.http_backoff_max_s)
            wait_s *= 1 + 0.25 * random.random()  # jitter: parallel requests do not retry in step
            log.warning(
                "%s: attempt %d/%d failed (%s); retrying in %.1f s", service, attempt, tries, last, wait_s
            )
            time.sleep(wait_s)
    error = UpstreamTimeout if timed_out else UpstreamError
    raise error(
        f"{SERVICE_NAMES.get(service, service)} is not answering right now ({tries} attempts). "
        "This is on their side; try again in a minute.",
        detail={"service": service, "reason": str(last)[:200]},
    )


def fetch_text(service: str, url: str, *, params: Params | None = None, tries: int | None = None) -> str:
    return fetch(service, url, params=params, tries=tries).text


def fetch_range(service: str, url: str, start: int, stop: int, *, tries: int | None = None) -> bytes:
    """Bytes start..stop-1 of a file (HTTP Range), with the same retries as `fetch`."""
    response = fetch(service, url, headers={"Range": f"bytes={start}-{stop - 1}"}, tries=tries)
    return response.content
