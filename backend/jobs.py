"""In-process background jobs. Each analysis run is an asyncio task on the server's event loop."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any


class JobManager:
    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}
        self._cancel: dict[str, asyncio.Event] = {}

    def start(self, job_id: str, factory: Callable[[asyncio.Event], Coroutine[Any, Any, None]]) -> None:
        cancel = asyncio.Event()
        task = asyncio.create_task(factory(cancel), name=f"run-{job_id}")
        self._tasks[job_id] = task
        self._cancel[job_id] = cancel
        task.add_done_callback(lambda _t: self._forget(job_id))

    def cancel(self, job_id: str) -> bool:
        event = self._cancel.get(job_id)
        if event is None:
            return False
        event.set()  # cooperative: the pipeline stops at its next checkpoint
        return True

    def is_active(self, job_id: str) -> bool:
        return job_id in self._tasks

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def _forget(self, job_id: str) -> None:
        self._tasks.pop(job_id, None)
        self._cancel.pop(job_id, None)
