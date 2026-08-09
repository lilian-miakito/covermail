"""Bounded in-memory jobs and event streams for heavy local model work."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any


class JobCancelled(Exception):
    """Internal cooperative-cancellation signal."""


@dataclass(slots=True)
class Job:
    id: str
    kind: str
    state: str = "queued"
    result: dict[str, Any] | None = None
    error: str | None = None
    internal_error: Exception | None = None
    cancelled: bool = False
    events: list[dict[str, Any]] = field(default_factory=list)
    future: Future[None] | None = None
    condition: threading.Condition = field(default_factory=threading.Condition)

    def emit(self, event_type: str, **data: Any) -> None:
        with self.condition:
            self.events.append(
                {"id": len(self.events), "type": event_type, "job_id": self.id, **data}
            )
            self.condition.notify_all()

    def transition(self, state: str, **data: Any) -> None:
        self.state = state
        self.emit("state", state=state, **data)

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise JobCancelled

    def wait(self, cursor: int, timeout: float) -> tuple[list[dict[str, Any]], bool]:
        with self.condition:
            if cursor >= len(self.events) and self.state not in {"complete", "failed", "cancelled"}:
                self.condition.wait(timeout)
            return self.events[cursor:].copy(), self.state in {
                "complete",
                "failed",
                "cancelled",
            }

    def public(self) -> dict[str, Any]:
        value: dict[str, Any] = {"id": self.id, "kind": self.kind, "state": self.state}
        if self.state == "complete":
            value["result"] = self.result
        if self.state == "failed":
            value["error"] = self.error
        return value


JobWork = Callable[[Job], dict[str, Any]]


class JobManager:
    """Serialize MLX access and retain only a small number of local jobs."""

    def __init__(self, *, maximum_jobs: int = 24, maximum_pending: int = 4) -> None:
        self._maximum_jobs = maximum_jobs
        self._maximum_pending = maximum_pending
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="covermail-model")

    def submit(self, kind: str, work: JobWork) -> Job:
        with self._lock:
            active = sum(
                job.state not in {"complete", "failed", "cancelled"} for job in self._jobs.values()
            )
            if active >= self._maximum_pending:
                raise RuntimeError("model job queue is full")
            self._trim_locked()
            job = Job(uuid.uuid4().hex, kind)
            job.emit("state", state="queued")
            self._jobs[job.id] = job
            job.future = self._executor.submit(self._run, job, work)
            return job

    def _run(self, job: Job, work: JobWork) -> None:
        try:
            job.check_cancelled()
            result = work(job)
            job.check_cancelled()
            job.result = result
            job.transition("complete")
        except JobCancelled:
            job.transition("cancelled")
        except Exception as error:
            job.internal_error = error
            job.error = "The local operation failed. Check the inputs and model compatibility."
            job.transition("failed")

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            job.cancelled = True
            if job.future is not None and job.future.cancel():
                job.transition("cancelled")
            return True

    def discard(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.state not in {"complete", "failed", "cancelled"}:
                job.cancelled = True
                return True
            del self._jobs[job_id]
            return True

    def _trim_locked(self) -> None:
        if len(self._jobs) < self._maximum_jobs:
            return
        for job_id, job in list(self._jobs.items()):
            if job.state in {"complete", "failed", "cancelled"}:
                del self._jobs[job_id]
                if len(self._jobs) < self._maximum_jobs:
                    return
        if len(self._jobs) >= self._maximum_jobs:
            raise RuntimeError("local job history is full")

    def shutdown(self) -> None:
        with self._lock:
            for job in self._jobs.values():
                job.cancelled = True
        self._executor.shutdown(wait=False, cancel_futures=True)
