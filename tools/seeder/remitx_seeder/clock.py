"""Replaying past days.

`SimClock` moves the whole process's clock with `time-machine`, so the
backend's own `datetime.now(UTC)` calls stamp the replayed moment, with no
change to the backend. It ticks while travelling, so two writes in one event
still get distinct, ordered timestamps.

Some calls must see the real time: S3 request signing (a request signed seven
weeks ago is rejected as skewed) and anything else that talks to a service
checking timestamps. Those run inside `SimClock.real_time()`.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import time_machine


class SimClock:
    def __init__(self) -> None:
        self._traveller: time_machine.travel | None = None

    @property
    def travelling(self) -> bool:
        return self._traveller is not None

    def move_to(self, moment: datetime) -> None:
        if moment.tzinfo is None:
            raise ValueError("SimClock needs timezone-aware datetimes")
        self.stop()
        self._traveller = time_machine.travel(moment, tick=True)
        self._traveller.start()

    def stop(self) -> None:
        if self._traveller is not None:
            self._traveller.stop()
            self._traveller = None

    def now(self) -> datetime:
        return datetime.now(UTC)

    @contextmanager
    def real_time(self) -> Iterator[None]:
        """Run the block on the real clock, then resume the replay where it was."""
        if self._traveller is None:
            yield
            return
        resume_at = datetime.now(UTC)
        self.stop()
        try:
            yield
        finally:
            self.move_to(resume_at)
