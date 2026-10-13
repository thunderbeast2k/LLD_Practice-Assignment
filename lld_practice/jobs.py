"""Where evaluation runs. Inline for tests/CLI; a small thread pool for the web app.
Swap for a real queue (RQ/Celery/SQS) by implementing JobRunner.submit - nothing else changes."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)


class JobRunner(ABC):
    @abstractmethod
    def submit(self, fn, *args) -> None: ...


class InlineRunner(JobRunner):
    def submit(self, fn, *args) -> None:
        fn(*args)


class ThreadRunner(JobRunner):
    def __init__(self, workers: int = 2):
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="eval")

    def submit(self, fn, *args) -> None:
        def guarded():
            try:
                fn(*args)
            except Exception:  # service handles expected failures; this is the last safety net
                log.exception("background job crashed")
        self._pool.submit(guarded)

    def shutdown(self) -> None:
        self._pool.shutdown(wait=True)
