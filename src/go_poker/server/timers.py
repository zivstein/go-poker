"""The next-hand pause, as a seam (ADR 0005 §10, C6.4 Brief §2.5).

The runtime arms one pending call per table and re-arms or cancels it after every operation. Only the scheduling is
behind this seam: *when* to arm, *what* to pass and what a stale firing means are the runtime's rules.

This module imports nothing else from the server, so `config` can hold the production scheduler as a default without
a cycle. The test scheduler lives in `tests/server/conftest.py`: no double belongs in production code.
"""

import asyncio
from collections.abc import Callable
from typing import Protocol


class NextHandScheduler(Protocol):
    """One pending next-hand call. `arm` replaces any armed call; `cancel` leaves none armed."""

    def arm(self, delay: float, fire: Callable[[], None]) -> None: ...

    def cancel(self) -> None: ...


class AsyncioNextHandScheduler:
    """The production scheduler: `loop.call_later` on the running loop, with its handle held so it can be cancelled.

    `arm` and `cancel` are synchronous, so phase 1 can use them without an `await` (ADR 0008 §4).
    """

    def __init__(self) -> None:
        self._handle: asyncio.TimerHandle | None = None

    def arm(self, delay: float, fire: Callable[[], None]) -> None:
        self.cancel()
        self._handle = asyncio.get_running_loop().call_later(delay, fire)

    def cancel(self) -> None:
        if self._handle is not None:
            self._handle.cancel()
            self._handle = None
