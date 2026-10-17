"""Return dead job graphs and unused native heap pages to the operating system."""

import ctypes
import gc
import logging
from pathlib import Path
import threading
import time


_LOCK = threading.Lock()
_NEXT_CHECK = 0.0
try:
    _TRIM = ctypes.CDLL(None).malloc_trim
    _TRIM.argtypes = [ctypes.c_size_t]
    _TRIM.restype = ctypes.c_int
except AttributeError:
    _TRIM = None


def resident_bytes():
    try:
        for line in Path('/proc/self/status').read_text().splitlines():
            if line.startswith('VmRSS:'):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    return 0


def release_unused_memory():
    global _NEXT_CHECK
    now = time.monotonic()
    if now < _NEXT_CHECK or not _LOCK.acquire(blocking=False):
        return
    try:
        if now < _NEXT_CHECK:
            return
        _NEXT_CHECK = now + 60
        before = resident_bytes()
        if before < 256 * 1024 * 1024:
            return
        # PRAW objects and exception tracebacks can form cycles and survive
        # into the oldest GC generation while executor threads stay alive.
        collected = gc.collect()
        if _TRIM is not None:
            _TRIM(0)
        after = resident_bytes()
        logging.info('Memory maintenance: RSS %.1f -> %.1f MiB; collected %d objects',
                     before / 2**20, after / 2**20, collected)
    finally:
        _LOCK.release()
