"""From what the user typed (a name, or RA/Dec in any usual format) to a position SPHEREx can be asked for.

Named objects come from Sesame (CDS, SIMBAD). Nearby stars move: Barnard's Star is ~4.5' away from
its J2000 position today, so the position returned is the one at `settings.reference_mjd`
(middle of the SPHEREx data), together with the proper motion so each image can mark where the
object should be. Ported from validation/notebooks/maxi/01_exploratory.ipynb (cell 1).
"""

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from urllib.parse import quote

import astropy.units as u
from astropy.coordinates import Angle, Distance, SkyCoord
from astropy.time import Time

from ..config import get_settings
from ..core import cache
from ..core.http import fetch_text
from ..errors import BadRequest, TargetNotFound

MJD_J2000 = 51544.5
DAYS_PER_YEAR = 365.25
MAS_PER_DEG = 3.6e6

# Short names people use that SIMBAD does not know, written without spaces or dashes in lower case.
ALIASES = {
    "wise0855": "WISE J085510.83-071442.5",
    "wise08550714": "WISE J085510.83-071442.5",
    "wisej08550714": "WISE J085510.83-071442.5",
    "w0855": "WISE J085510.83-071442.5",
}


@dataclass(frozen=True)
class Target:
    name: str | None
    ra_deg: float  # ICRS, at epoch_mjd
    dec_deg: float
    epoch_mjd: float
    pm_ra_masyr: float | None  # includes cos(dec)
    pm_dec_masyr: float | None
    parallax_mas: float | None
    catalog_ra_deg: float  # as given by the catalogue (J2000) or as typed
    catalog_dec_deg: float
    object_type: str | None
    source: str  # "sesame" or "coordinates"

    def to_dict(self) -> dict:
        return asdict(self)


def parse_coordinates(ra: str, dec: str) -> tuple[float, float]:
    """Decimal degrees ("133.795", "-7.245") or sexagesimal ("08h55m10.831s", "-7d14m42.53s",
    "08 55 10.8", "-07 14 42"). Sexagesimal RA without a unit is read as hours."""
    try:
        ra_text, dec_text = ra.strip(), dec.strip()
        try:
            ra_deg = float(ra_text)
        except ValueError:
            is_degrees = "d" in ra_text.lower() or "°" in ra_text
            ra_deg = Angle(ra_text, unit=u.deg if is_degrees else u.hourangle).deg
        try:
            dec_deg = float(dec_text)
        except ValueError:
            dec_deg = Angle(dec_text, unit=u.deg).deg
    except Exception as e:  # astropy raises several types for unreadable text
        raise BadRequest(
            "Could not read the coordinates. Use decimal degrees or 08h55m10.8s -7d14m42s.",
            detail={"ra": ra, "dec": dec},
        ) from e
    if not (0 <= ra_deg < 360 and -90 <= dec_deg <= 90):
        raise BadRequest("Coordinates out of range (RA 0–360°, Dec −90–90°).", detail={"ra": ra, "dec": dec})
    return float(ra_deg), float(dec_deg)


def propagate(
    ra_deg: float, dec_deg: float, pm_ra_masyr: float, pm_dec_masyr: float, from_mjd: float, to_mjd: float
) -> tuple[float, float]:
    """Linear proper motion, good to well under 0.01" over the few years of SPHEREx data.
    Parallax is ignored (0.55" for Barnard's Star, a tenth of a pixel)."""
    years = (to_mjd - from_mjd) / DAYS_PER_YEAR
    dec = dec_deg + pm_dec_masyr * years / MAS_PER_DEG
    ra = ra_deg + pm_ra_masyr * years / MAS_PER_DEG / math.cos(math.radians(dec_deg))
    return ra % 360.0, dec


def from_coordinates(ra: str, dec: str) -> Target:
    ra_deg, dec_deg = parse_coordinates(ra, dec)
    return Target(
        name=None,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        epoch_mjd=get_settings().reference_mjd,
        pm_ra_masyr=None,
        pm_dec_masyr=None,
        parallax_mas=None,
        catalog_ra_deg=ra_deg,
        catalog_dec_deg=dec_deg,
        object_type=None,
        source="coordinates",
    )


def _number(node: ET.Element | None, path: str) -> float | None:
    found = node.find(path) if node is not None else None
    try:
        return float(found.text) if found is not None and found.text else None
    except ValueError:
        return None


def parse_sesame(xml: str, name: str) -> Target:
    """Sesame XML (-oxp) → Target. Positions from SIMBAD are ICRS at epoch J2000."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise TargetNotFound(f'Could not look up "{name}".', detail={"name": name}) from e
    resolver = next((r for r in root.iter("Resolver") if r.find("jradeg") is not None), None)
    ra0, dec0 = _number(resolver, "jradeg"), _number(resolver, "jdedeg")
    if ra0 is None or dec0 is None:
        raise TargetNotFound(
            f'No object called "{name}" was found. Check the spelling or enter coordinates.',
            detail={"name": name},
        )
    pm_ra, pm_dec = _number(resolver, "pm/pmRA"), _number(resolver, "pm/pmDE")
    parallax = _number(resolver, "plx/v")
    reference_mjd = get_settings().reference_mjd
    ra, dec = ra0, dec0
    if pm_ra is not None and pm_dec is not None:
        star = SkyCoord(
            ra0 * u.deg,
            dec0 * u.deg,
            pm_ra_cosdec=pm_ra * u.mas / u.yr,
            pm_dec=pm_dec * u.mas / u.yr,
            distance=Distance(parallax=parallax * u.mas) if parallax and parallax > 0 else 1 * u.kpc,
            obstime=Time("J2000"),
        )
        moved = star.apply_space_motion(new_obstime=Time(reference_mjd, format="mjd"))
        ra, dec = float(moved.ra.deg), float(moved.dec.deg)
    official = resolver.findtext("oname") if resolver is not None else None
    return Target(
        name=(official or name).strip(),
        ra_deg=ra,
        dec_deg=dec,
        epoch_mjd=reference_mjd,
        pm_ra_masyr=pm_ra,
        pm_dec_masyr=pm_dec,
        parallax_mas=parallax,
        catalog_ra_deg=ra0,
        catalog_dec_deg=dec0,
        object_type=resolver.findtext("otype") if resolver is not None else None,
        source="sesame",
    )


def from_name(name: str) -> Target:
    name = " ".join(name.split())
    if not name or len(name) > 80:
        raise BadRequest("Enter an object name (up to 80 characters).")
    name = ALIASES.get(re.sub(r"[\s\-−–+]", "", name.lower()), name)
    s = get_settings()
    key = cache.make_key("sesame", name.lower(), s.reference_mjd)
    data = cache.get("resolve", key, s.resolve_cache_ttl_s)
    if data is None:
        xml = fetch_text("cds-sesame", s.sesame_url + quote(name))
        data = parse_sesame(xml, name).to_dict()
        cache.put("resolve", key, data)
    return Target(**data)
