"""Sources from other missions around a position, to overlay on the SPHEREx images.

- Gaia DR3 from the ESA archive (TAP): positions at epoch 2016.0 with proper motions.
- AllWISE from IRSA (cone search): positions around 2010.5, mid-infrared magnitudes.

Both verified live on 2026-11-14. The brightest `limit` sources are returned.
"""

import csv
import io

from ..config import get_settings
from ..core import cache
from ..core.http import fetch_text

CATALOGS = ("gaia", "wise")


def _rows(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))


def _float(value: str | None) -> float | None:
    try:
        number = float(value) if value not in (None, "", "null") else None
    except ValueError:
        return None
    return number if number is None or number == number else None  # drop NaN


def _gaia(ra_deg: float, dec_deg: float, radius_deg: float, limit: int) -> list[dict]:
    query = (
        f"SELECT TOP {int(limit)} source_id, ra, dec, pmra, pmdec, phot_g_mean_mag, ref_epoch "
        "FROM gaiadr3.gaia_source WHERE 1=CONTAINS(POINT('ICRS', ra, dec), "
        f"CIRCLE('ICRS', {ra_deg:.6f}, {dec_deg:.6f}, {radius_deg:.5f})) ORDER BY phot_g_mean_mag"
    )
    params = {"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": query}
    sources = []
    for row in _rows(fetch_text("esa-gaia", get_settings().gaia_tap_url, params=params)):
        ra, dec = _float(row.get("ra")), _float(row.get("dec"))
        if ra is None or dec is None:
            continue
        sources.append(
            {
                "id": f"Gaia DR3 {row.get('source_id', '')}",
                "ra_deg": ra,
                "dec_deg": dec,
                "pm_ra_masyr": _float(row.get("pmra")),
                "pm_dec_masyr": _float(row.get("pmdec")),
                "epoch_jyear": _float(row.get("ref_epoch")) or 2016.0,
                "mag": _float(row.get("phot_g_mean_mag")),
                "band": "G",
            }
        )
    return sources


def _wise(ra_deg: float, dec_deg: float, radius_deg: float, limit: int) -> list[dict]:
    params = {
        "table": "allwise_p3as_psd",
        "RA": f"{ra_deg:.6f}",
        "DEC": f"{dec_deg:.6f}",
        "SR": f"{radius_deg:.5f}",
        "format": "csv",
    }
    sources = []
    for row in _rows(fetch_text("irsa-scs", get_settings().irsa_scs_url, params=params)):
        ra, dec = _float(row.get("ra")), _float(row.get("dec"))
        if ra is None or dec is None:
            continue
        sources.append(
            {
                "id": f"WISEA {row.get('designation', '')}",
                "ra_deg": ra,
                "dec_deg": dec,
                "pm_ra_masyr": None,  # AllWISE motions are not reliable enough to move the marker
                "pm_dec_masyr": None,
                "epoch_jyear": 2010.5,
                "mag": _float(row.get("w1mpro")),
                "band": "W1",
            }
        )
    sources.sort(key=lambda s: s["mag"] if s["mag"] is not None else 99.0)
    return sources[:limit]


def cone(catalog: str, ra_deg: float, dec_deg: float, radius_deg: float) -> list[dict]:
    """Brightest sources of `catalog` ("gaia" or "wise") inside the circle. Cached on disk."""
    s = get_settings()
    key = cache.make_key("overlay", catalog, ra_deg, dec_deg, radius_deg, s.max_overlay_sources)
    load = _gaia if catalog == "gaia" else _wise
    return cache.cached(
        "overlay",
        key,
        s.overlay_cache_ttl_s,
        lambda: load(ra_deg, dec_deg, radius_deg, s.max_overlay_sources),
    )
