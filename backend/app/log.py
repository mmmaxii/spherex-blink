"""Logging setup: one line per event on stdout (what Render collects)."""

import logging

from .config import get_settings


def setup_logging() -> None:
    logging.basicConfig(
        level=get_settings().log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )
    # astropy announces harmless header quirks of SPHEREx files at INFO on every image.
    # Its logger must be reached through astropy itself: logging.getLogger("astropy") before
    # astropy is imported creates a plain Logger and astropy then fails to start.
    import astropy

    astropy.log.setLevel("WARNING")
    for noisy in ("httpx", "httpcore", "fsspec", "aiohttp", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
