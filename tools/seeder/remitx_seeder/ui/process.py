"""Running one runner command in a child process and following its output."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass, field

from remitx_seeder.settings import SEEDER_ROOT

OnEvent = Callable[[dict], None]


@dataclass
class CommandOutcome:
    ok: bool
    result: dict | None = None
    error: str | None = None
    guards: dict | None = None
    events: list[dict] = field(default_factory=list)


async def run_command(
    command: str, target: str, *args: str, on_event: OnEvent | None = None
) -> CommandOutcome:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "remitx_seeder",
        command,
        "--target",
        target,
        *args,
        cwd=SEEDER_ROOT,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        # A seed run's result line carries the whole manifest; the default
        # 64 KiB line limit is too small for it.
        limit=64 * 1024 * 1024,
    )
    outcome = CommandOutcome(ok=False)
    assert process.stdout is not None
    while True:
        raw = await process.stdout.readline()
        if not raw:
            break
        line = raw.decode(errors="replace").rstrip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            event = {"type": "log", "level": "debug", "message": line}
        if event.get("type") == "result":
            outcome.result = event.get("result")
        elif event.get("type") == "error":
            outcome.error = event.get("message")
        elif event.get("type") == "guards":
            outcome.guards = event
        outcome.events.append(event)
        if on_event is not None:
            on_event(event)
    await process.wait()
    outcome.ok = process.returncode == 0 and outcome.error is None
    if process.returncode != 0 and outcome.error is None:
        outcome.error = f"exited with status {process.returncode}"
    return outcome
