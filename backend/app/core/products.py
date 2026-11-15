"""Files a pipeline produces for the browser (PNG frames, GIF, manifest), kept on disk by request key.

    <cache_dir>/products/<kind>/<key>/manifest.json   written last: its presence means "complete"
    <cache_dir>/products/<kind>/<key>/frame_000.png   served at /api/products/<kind>/<key>/frame_000.png

The key is a hash of the request parameters, so the same request is served from disk the second
time. The disk on Render is temporary; losing these files only means computing them again.
"""

import json
import logging
import re
import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..errors import NotFound
from .cache import write_json_atomic

log = logging.getLogger(__name__)

_SAFE_KEY = re.compile(r"^[a-f0-9]{8,40}$")
_SAFE_KIND = re.compile(r"^[a-z]{2,20}$")
_SAFE_NAME = re.compile(r"^[a-z0-9_]{1,40}\.(png|gif|json|csv|bin)$")
MANIFEST = "manifest.json"


class ProductStore:
    def __init__(self, root: Path, max_products: int):
        self.root = root
        self.max_products = max_products

    def folder(self, kind: str, key: str) -> Path:
        if not (_SAFE_KIND.match(kind) and _SAFE_KEY.match(key)):
            raise NotFound("No such product.")
        return self.root / kind / key

    def new_folder(self, kind: str, key: str) -> Path:
        """Empty folder for a job that is about to write its files."""
        folder = self.folder(kind, key)
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def file(self, kind: str, key: str, name: str) -> Path:
        """Path of a product file requested from outside; rejects anything that is not a plain name."""
        if not _SAFE_NAME.match(name):
            raise NotFound("No such product.")
        path = self.folder(kind, key) / name
        if not path.is_file():
            raise NotFound("This result is no longer stored. Run the search again.")
        return path

    @staticmethod
    def url(kind: str, key: str, name: str) -> str:
        return f"/api/products/{kind}/{key}/{name}"

    def load_manifest(self, kind: str, key: str) -> dict[str, Any] | None:
        try:
            return json.loads((self.folder(kind, key) / MANIFEST).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def save_manifest(self, kind: str, key: str, manifest: dict[str, Any]) -> None:
        write_json_atomic(self.folder(kind, key) / MANIFEST, manifest)
        self.prune()

    def prune(self) -> None:
        """Keep the newest `max_products` folders."""
        try:
            folders = [
                f for kind in self.root.iterdir() if kind.is_dir() for f in kind.iterdir() if f.is_dir()
            ]
            folders.sort(key=lambda f: f.stat().st_mtime, reverse=True)
            for old in folders[self.max_products :]:
                shutil.rmtree(old, ignore_errors=True)
        except OSError as e:
            log.warning("could not prune products: %s", e)


@lru_cache
def get_product_store() -> ProductStore:
    s = get_settings()
    return ProductStore(Path(s.cache_dir) / "products", s.max_products)
