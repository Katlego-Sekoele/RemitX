"""The replay loop: a queue of timed events, run in order.

An event is a moment and a callable. Running it moves the clock to that moment,
opens a database session the way a request would, calls the backend, and
closes the session. An event may schedule follow-ups (a submission schedules
its review; a deposit schedules the sends it pays for). Anything scheduled past
the end of the window is dropped, which is exactly how "still waiting for a
reviewer" and "quote not yet confirmed" states arise.

A refusal by the backend (a domain error such as a limit or a failed check) is
recorded and the run carries on: it means the generator asked for something
the rules forbid, which `verify` and the manifest make visible.
"""

from __future__ import annotations

import heapq
import itertools
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from remitx_seeder.context import RunContext

PROGRESS_EVERY = 25


@dataclass(order=True)
class Event:
    at: datetime
    seq: int
    name: str = field(compare=False)
    action: Callable[[], None] = field(compare=False)


class Simulation:
    def __init__(self, ctx: RunContext) -> None:
        self.ctx = ctx
        self._queue: list[Event] = []
        self._seq = itertools.count()
        self.done = 0
        self.dropped = 0
        self.now: datetime | None = None

    def schedule(self, at: datetime, name: str, action: Callable[[], None]) -> None:
        if at > self.ctx.window_end:
            self.dropped += 1
            return
        if self.now is not None and at < self.now:
            at = self.now
        heapq.heappush(self._queue, Event(at, next(self._seq), name, action))

    def run(self) -> None:
        from remitx_api.extensions import db

        while self._queue:
            event = heapq.heappop(self._queue)
            # The clock ticks while an event runs; never step back behind what
            # the previous event already stamped.
            moment = event.at
            if self.ctx.clock.travelling:
                moment = max(moment, self.ctx.clock.now())
            self.now = moment
            self.ctx.clock.move_to(moment)
            token = db.open_session()
            try:
                event.action()
                self.ctx.count(f"events.{event.name}")
            except Exception as exc:  # noqa: BLE001 — recorded, run carries on
                db.session.rollback()
                self._record_refusal(event, exc)
            finally:
                db.close_session(token)
            self.done += 1
            if self.done % PROGRESS_EVERY == 0 or not self._queue:
                self.ctx.emit(
                    {
                        "type": "progress",
                        "done": self.done,
                        "queued": len(self._queue),
                        "at": event.at.isoformat(),
                    }
                )
        self.ctx.clock.stop()

    def _record_refusal(self, event: Event, exc: Exception) -> None:
        refusal = {
            "event": event.name,
            "at": event.at.isoformat(),
            "error": type(exc).__name__,
            "message": str(exc)[:300],
        }
        if not _is_domain_error(exc):
            refusal["traceback"] = traceback.format_exc(limit=6)
        self.ctx.refusals.append(refusal)
        self.ctx.count("refusals")
        self.ctx.log(
            f"{event.name} refused at {event.at:%Y-%m-%d %H:%M}: "
            f"{type(exc).__name__}: {str(exc)[:160]}",
            level="warning",
        )


def _is_domain_error(exc: Exception) -> bool:
    module = type(exc).__module__
    return module.startswith("remitx_api.errors") or module.startswith(
        "remitx_api.services"
    )
