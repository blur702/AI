from __future__ import annotations

import queue
import threading
from typing import Any, Callable, Optional


class PollingThread(threading.Thread):
    """Background polling worker that periodically calls a function.

    The function's return value (if not None) is pushed into a queue for the UI
    thread to consume.
    """

    def __init__(
        self,
        name: str,
        interval: float,
        func: Callable[[], Any],
        out_queue: Optional[queue.Queue] = None,
    ) -> None:
        super().__init__(name=name, daemon=True)
        self.interval = interval
        self.func = func
        self.out_queue = out_queue
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                result = self.func()
                if self.out_queue is not None and result is not None:
                    self.out_queue.put(result)
            except Exception:
                # Swallow exceptions to keep the polling loop alive.
                pass
            # Simple fixed-interval polling
            self._stop_event.wait(self.interval)


def start_poller(
    name: str,
    interval: float,
    func: Callable[[], Any],
    out_queue: Optional[queue.Queue] = None,
) -> PollingThread:
    """Helper to create and start a PollingThread."""
    worker = PollingThread(name=name, interval=interval, func=func, out_queue=out_queue)
    worker.start()
    return worker

