"""Request-local timings: no waveform, names, paths or credentials."""
from contextvars import ContextVar
from contextlib import contextmanager
from time import perf_counter

current = ContextVar("mcp_timings", default=None)


@contextmanager
def measure(stage):
    start = perf_counter()
    try:
        yield
    finally:
        timings = current.get()
        if timings is not None:
            timings[stage] = timings.get(stage, 0) + (perf_counter() - start) * 1000
