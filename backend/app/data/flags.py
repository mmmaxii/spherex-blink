"""Pixel flags of L2 images: names read from the file, and the official masking recipe.

The FLAGS extension is a bit mask; the name of each bit is in its header as MSKNnnnn (not MP_*).
Ported from 01_exploratory.ipynb (cell 7), where it was checked on a DR1 image.
"""

import numpy as np

# Official recipe for photometry (SPHEREx Explanatory Supplement): pixels with any of these flags
# are not used. TRANSIENT, OVERFLOW, OUTLIER and SOURCE are kept; SOURCE also marks known
# asteroids, so a target must never be discarded because of it.
EXCLUDE_FOR_PHOTOMETRY = (
    "SUR_ERROR",
    "NONFUNC",
    "MISSING_DATA",
    "HOT",
    "COLD",
    "NONLINEAR",
    "PERSIST",
    "BLOOM",
    "SNOWBALL",
    "HALO",
    "SATELLITE_HALO",
)

# Flags of the detector itself (dead, hot or cold pixels), not of the sky. They are isolated pixels
# at a fixed place on the detector, so a stack of several images would keep them. The other flags
# of the recipe mostly sit on and around stars (HALO, SUR_ERROR, BLOOM, and PERSIST when two
# exposures point almost the same way) and hold real starlight. Stacks hide only these
# (imaging/stack.py explains why).
DETECTOR_DEFECTS = ("NONFUNC", "MISSING_DATA", "HOT", "COLD")


def bit_names(flags_header) -> dict[int, str]:
    """{bit index: name} from the MSKNnnnn keys of the FLAGS header.
    VERIFY: the number in the key is taken as the bit index (bit 21 = SOURCE matched 73 % of a
    crowded cutout, as expected, in 01_exploratory.ipynb)."""
    bits = {}
    for key, value in flags_header.items():
        if key.startswith("MSKN") and key[4:].isdigit():
            bits[int(key[4:])] = str(value).strip()
    return bits


def bad_mask(flags: np.ndarray, bits: dict[int, str], exclude=EXCLUDE_FOR_PHOTOMETRY) -> np.ndarray:
    """True where a pixel has any flag of the recipe."""
    value = sum(1 << bit for bit, name in bits.items() if name in exclude)
    return (flags.astype(np.int64) & value) != 0


def count_flags(flags: np.ndarray, bits: dict[int, str]) -> dict[str, int]:
    """{flag name: number of pixels} for the flags present in the array."""
    values = flags.astype(np.int64)
    counts = {}
    for bit, name in sorted(bits.items()):
        n = int(((values >> bit) & 1).sum())
        if n:
            counts[name] = n
    return counts


def names_at(flags: np.ndarray, bits: dict[int, str], row: int, col: int) -> list[str]:
    """Flag names set on one pixel; empty if the pixel is outside the array."""
    if not (0 <= row < flags.shape[0] and 0 <= col < flags.shape[1]):
        return []
    value = int(flags[row, col])
    return [name for bit, name in sorted(bits.items()) if (value >> bit) & 1]
