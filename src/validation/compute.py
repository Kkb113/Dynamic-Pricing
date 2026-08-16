from __future__ import annotations

import os
import platform
import sys
from contextlib import contextmanager
from typing import Any, Iterator

import numpy as np

try:
    import psutil
except ImportError:  # pragma: no cover - dependency is declared, fallback is defensive
    psutil = None

try:
    from threadpoolctl import threadpool_limits
except ImportError:  # pragma: no cover - dependency is declared, fallback is defensive
    @contextmanager
    def threadpool_limits(limits: int | None = None, user_api: str | None = None) -> Iterator[None]:
        yield


MAX_CPU_THREADS = 22
THREAD_ENVIRONMENT_KEYS = ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS")


def detect_compute_environment(max_threads: int = MAX_CPU_THREADS) -> dict[str, Any]:
    logical = int(psutil.cpu_count(logical=True) if psutil is not None else (os.cpu_count() or 1))
    physical_value = psutil.cpu_count(logical=False) if psutil is not None else None
    physical = int(physical_value or logical)
    usable = max(1, min(logical, int(max_threads)))
    return {
        "python_version": sys.version,
        "numpy_version": np.__version__,
        "platform": platform.platform(),
        "detected_physical_cores": physical,
        "detected_logical_threads": logical,
        "configured_thread_limit": int(max_threads),
        "usable_threads": usable,
        "effective_parallelism": "single_fit_at_a_time_with_threadpool_limit",
        "nested_parallelism": False,
        "thread_environment": {key: os.environ.get(key) for key in THREAD_ENVIRONMENT_KEYS},
    }


def configure_thread_environment(environment: dict[str, Any]) -> dict[str, Any]:
    """Set one BLAS/OpenMP limit for the run and return the enriched environment."""
    value = str(int(environment["usable_threads"]))
    configured: dict[str, str] = {}
    for key in THREAD_ENVIRONMENT_KEYS:
        os.environ[key] = value
        configured[key] = value
    environment["thread_environment"] = configured
    environment["configured_thread_limit"] = min(int(environment["configured_thread_limit"]), int(environment["detected_logical_threads"]))
    return environment


@contextmanager
def thread_limited(environment: dict[str, Any]) -> Iterator[None]:
    """Limit BLAS/OpenMP work for one fit without creating nested parallel jobs."""
    with threadpool_limits(limits=int(environment["usable_threads"])):
        yield
