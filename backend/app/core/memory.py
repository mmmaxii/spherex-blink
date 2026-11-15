"""Keep the process small on Render's 512 MB instance (Linux, glibc).

Jobs read images in 12 threads. glibc gives each thread its own memory pool and, once a few
large arrays have been freed, starts serving arrays of a few MB from those pools, which it rarely
hands back to the system: the process keeps growing after every job even though Python freed
everything. Two settings fix that, and a trim after each job returns what is left:

- at most 2 pools (M_ARENA_MAX), shared by all threads;
- arrays larger than 128 KB always get their own block (M_MMAP_THRESHOLD), returned when freed.

On other systems (Windows, macOS: local development) these calls are skipped.
"""

import ctypes
import ctypes.util
import logging
import sys

log = logging.getLogger(__name__)

M_MMAP_THRESHOLD = -3  # mallopt parameter numbers from glibc's malloc.h
M_ARENA_MAX = -8
MMAP_THRESHOLD_BYTES = 128 * 1024
ARENA_MAX = 2

_libc = None


def _glibc():
    """The C library when it is glibc (Linux), else None."""
    global _libc
    if _libc is None and sys.platform.startswith("linux"):
        try:
            _libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6")
            _libc.malloc_trim  # noqa: B018 - only glibc has it
        except (OSError, AttributeError):
            _libc = False
    return _libc or None


def limit_pools() -> None:
    """Apply the two settings above. Call once at start-up, before the job threads exist."""
    libc = _glibc()
    if libc:
        libc.mallopt(M_ARENA_MAX, ARENA_MAX)
        libc.mallopt(M_MMAP_THRESHOLD, MMAP_THRESHOLD_BYTES)
        kb = MMAP_THRESHOLD_BYTES // 1024
        log.info("malloc: %d pools, arrays above %d KB returned when freed", ARENA_MAX, kb)


def give_back() -> None:
    """Return freed memory to the system (called when a job ends)."""
    libc = _glibc()
    if libc:
        libc.malloc_trim(0)
