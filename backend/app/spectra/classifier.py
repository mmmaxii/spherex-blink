"""What kind of object a spectrum belongs to.

NOT BUILT YET. This module is the slot for the trained model: it is loaded once from
`<model_dir>/<classifier_file>` (joblib) and applied to every spectrum pipeline/spectrum.py
produces. With no model file, spectra are returned without a classification.

Expected content of the joblib file (decided when the model is trained; adjust here if it changes):
    {"model": <fitted scikit-learn estimator>, "features": [...], "classes": [...], "version": "..."}
"""

import logging
import threading
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..errors import NotBuilt

log = logging.getLogger(__name__)

_lock = threading.Lock()
_loaded: dict[str, Any] | None = None
_tried = False


@dataclass(frozen=True)
class Classification:
    label: str
    probability: float | None
    method: str  # e.g. "gradient boosting", "chi-square template fit"
    model_version: str | None
    alternatives: list[dict]  # [{"label": ..., "probability": ...}], best first

    def to_dict(self) -> dict:
        return asdict(self)


def model_path() -> Path:
    s = get_settings()
    return Path(s.model_dir) / s.classifier_file


def load_model() -> dict[str, Any] | None:
    """The model bundle, loaded on first use; None when there is no file (or it cannot be read)."""
    global _loaded, _tried
    with _lock:
        if not _tried:
            _tried = True
            path = model_path()
            if path.is_file():
                try:
                    import joblib

                    _loaded = joblib.load(path)
                    log.info("classifier loaded from %s", path)
                except Exception:  # noqa: BLE001 - a broken model file must not stop the API
                    log.exception("could not load the classifier at %s", path)
        return _loaded


def is_ready() -> bool:
    return load_model() is not None


def features(points: list[dict]) -> list[float]:
    """Spectrum points → the feature vector the model was trained on."""
    raise NotBuilt("The classifier's features are not defined yet.")


def classify(points: list[dict]) -> Classification | None:
    """Classification of one spectrum, or None when no model is installed."""
    bundle = load_model()
    if bundle is None:
        return None
    raise NotBuilt("A model file is present but classify() is not written yet.")
