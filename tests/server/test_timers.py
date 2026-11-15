"""The production next-hand scheduler (C6.4 Brief §2.5).

The runtime's own tests drive the test scheduler, so these exercise the real `loop.call_later` one: it fires once,
cancelling prevents it, and arming again replaces the pending call. Each test runs its own event loop, because
`arm` needs a running loop, as it has inside a request handler.
"""

import asyncio

from go_poker.server.timers import AsyncioNextHandScheduler

# Long enough for the loop to run a zero-delay call, short enough to keep the suite fast.
TICK = 0.05


def test_an_armed_call_fires_once() -> None:
    async def run() -> list[str]:
        fired: list[str] = []
        scheduler = AsyncioNextHandScheduler()
        scheduler.arm(0, lambda: fired.append("first"))
        await asyncio.sleep(TICK)
        return fired

    assert asyncio.run(run()) == ["first"]


def test_a_cancelled_call_never_fires() -> None:
    async def run() -> list[str]:
        fired: list[str] = []
        scheduler = AsyncioNextHandScheduler()
        scheduler.arm(TICK, lambda: fired.append("first"))
        scheduler.cancel()
        await asyncio.sleep(TICK * 2)
        return fired

    assert asyncio.run(run()) == []


def test_arming_again_replaces_the_pending_call() -> None:
    async def run() -> list[str]:
        fired: list[str] = []
        scheduler = AsyncioNextHandScheduler()
        scheduler.arm(TICK, lambda: fired.append("first"))
        scheduler.arm(0, lambda: fired.append("second"))
        await asyncio.sleep(TICK * 2)
        return fired

    assert asyncio.run(run()) == ["second"]


def test_cancelling_when_nothing_is_armed_is_harmless() -> None:
    scheduler = AsyncioNextHandScheduler()
    scheduler.cancel()
    scheduler.cancel()
