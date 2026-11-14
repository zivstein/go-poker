"""The runtime's bounded outbox, its failure isolation, and the durable proof that phase 1 never awaits.

ADR 0008 §3 and §4: phase 1 is one synchronous step per mutation, a slow client never delays another, and a defect
inside it takes down exactly one table.
"""

import ast
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import pytest

from go_poker.app.identity import DisplayName
from go_poker.core.card import Card
from go_poker.server import decode, dto
from go_poker.server.runtime import (
    CLOSE_LEFT_TABLE,
    CLOSE_OUTBOX_OVERFLOW,
    CLOSE_TABLE_FAILED,
    Connection,
    Frame,
    Outbox,
)

type Harness = Any  # `RuntimeHarness` from conftest, which a test module cannot import

SERVER_PACKAGE = Path(__file__).resolve().parents[2] / "src" / "go_poker" / "server"
# The modules phase 1 runs in. Everything they call must be synchronous too (ADR 0008 §4).
PHASE_ONE_MODULES = (SERVER_PACKAGE / "runtime.py", SERVER_PACKAGE / "timers.py")

ASYNC_NODES: tuple[type[ast.AST], ...] = (ast.Await, ast.AsyncFunctionDef, ast.AsyncFor, ast.AsyncWith)


def _snapshot_frame() -> Frame:
    """A frame whose content does not matter: these tests are about the queue, not the message."""
    return Frame(dto.Superseded(type="superseded"))


# --- The bounded outbox (ADR 0009 §5) ---


def test_an_outbox_needs_a_capacity() -> None:
    with pytest.raises(ValueError, match="capacity"):
        Outbox(0)


def test_an_outbox_keeps_its_frames_in_order() -> None:
    outbox = Outbox(3)
    first, second = _snapshot_frame(), _snapshot_frame()
    outbox.put(first)
    outbox.put(second)

    assert outbox.drain() == [first, second]
    assert outbox.drain() == []
    assert outbox.overflowed is False


def test_an_outbox_that_is_not_drained_overflows_and_drops_its_queue() -> None:
    outbox = Outbox(2)
    outbox.put(_snapshot_frame())
    outbox.put(_snapshot_frame())

    outbox.put(_snapshot_frame())

    assert outbox.overflowed is True
    assert len(outbox) == 0
    assert outbox.drain() == []


def test_an_overflowed_outbox_queues_nothing_more() -> None:
    outbox = Outbox(1)
    outbox.put(_snapshot_frame())
    outbox.put(_snapshot_frame())

    outbox.put(_snapshot_frame())

    assert outbox.overflowed is True
    assert outbox.drain() == []


def test_a_terminal_frame_ignores_the_capacity_and_never_overflows_the_outbox() -> None:
    outbox = Outbox(2)
    queued = [_snapshot_frame(), _snapshot_frame()]
    for frame in queued:
        outbox.put(frame)
    terminal = Frame(dto.LeftTable(type="left_table"), CLOSE_LEFT_TABLE)

    outbox.put_terminal(terminal)

    assert outbox.drain() == [*queued, terminal]
    assert outbox.overflowed is False


def test_the_overflow_close_code_is_the_contracts() -> None:
    assert CLOSE_OUTBOX_OVERFLOW == 4008


# --- Overflow on a live table ---


@pytest.fixture
def small_outboxes(
    make_runtime: Callable[..., Harness],
    scenario_setup: Callable[[str], Mapping[str, Any]],
    parse_cards: Callable[[Iterable[str]], list[Card]],
    queue_decks: Callable[..., Any],
) -> Callable[[int], Harness]:
    """A `heads_up_hand` table whose connections hold only a few frames."""

    def build(outbox_size: int) -> Harness:
        setup = scenario_setup("heads_up_hand")
        queue_decks(*(parse_cards(hand["draw_order"]) for hand in setup["hands"]))
        return make_runtime(setup, "alice", outbox_size=outbox_size)

    return build


def test_an_overflowing_connection_does_not_affect_another_connection_of_its_table(
    small_outboxes: Callable[[int], Harness],
    messages_of: Callable[[Connection], list[dict[str, Any]]],
) -> None:
    harness = small_outboxes(2)
    alice = harness.open("alice")  # one frame, never drained
    harness.join("bob", 2)  # alice is now at capacity
    bob = harness.open("bob")

    harness.execute(alice, decode.StartGame(request_id="a-02", expected_revision=2))

    assert alice.outbox.overflowed is True
    assert alice.outbox.drain() == []
    assert bob.outbox.overflowed is False
    assert [(message["type"], message["revision"]) for message in messages_of(bob)] == [
        ("snapshot", 2),
        ("snapshot", 3),
    ]
    assert harness.runtime.revision == 3, "a slow client does not stop the table"


def test_a_terminal_message_still_arrives_after_an_overflow_dropped_the_outcome(
    small_outboxes: Callable[[int], Harness],
) -> None:
    """An outbox that is already full when the outcome is queued loses the outcome, never `left_table`.

    ADR 0009 §8.3 allows an undelivered outcome, and the departure is the signal that matters: the member really
    left, so the writer closes `4410` rather than the overflow's `4008`, and the credential is revoked either way.
    """
    harness = small_outboxes(1)
    alice = harness.open("alice")  # the connected snapshot fills the outbox and is never drained

    harness.execute(alice, decode.Leave(request_id="a-01", expected_revision=1))

    frames = alice.outbox.drain()
    assert [frame.message.type for frame in frames] == ["left_table"], "the dropped outcome does not block the close"
    assert [frame.close_code for frame in frames] == [CLOSE_LEFT_TABLE]
    assert alice.outbox.overflowed is True
    assert alice.stopped is True
    assert harness.runtime.authenticate(harness.credentials["alice"]) is None


def test_an_outcome_and_a_terminal_message_both_arrive_at_a_full_outbox(
    small_outboxes: Callable[[int], Harness],
) -> None:
    harness = small_outboxes(2)
    alice = harness.open("alice")  # one frame, never drained

    harness.execute(alice, decode.Leave(request_id="a-01", expected_revision=1))

    frames = alice.outbox.drain()
    assert [frame.message.type for frame in frames] == ["snapshot", "accepted", "left_table"]
    assert [frame.close_code for frame in frames] == [None, None, CLOSE_LEFT_TABLE]
    assert alice.outbox.overflowed is False


# --- Failure isolation (C6.4 Brief §2.9) ---


@pytest.fixture
def two_tables(
    make_runtime: Callable[..., Harness],
    scenario_setup: Callable[[str], Mapping[str, Any]],
    parse_cards: Callable[[Iterable[str]], list[Card]],
    queue_decks: Callable[..., Any],
) -> tuple[Harness, Harness]:
    """Two independent tables, each with its own session, runtime, scheduler and connections."""
    setup = scenario_setup("heads_up_hand")
    queue_decks(*(parse_cards(hand["draw_order"]) for hand in setup["hands"]))
    first = make_runtime(setup, "alice")
    second = make_runtime(setup, "alice")
    for harness in (first, second):
        harness.join("bob", 2)
    return first, second


def test_a_defect_inside_phase_one_fails_only_its_own_table(
    two_tables: tuple[Harness, Harness],
    monkeypatch: pytest.MonkeyPatch,
    messages_of: Callable[[Connection], list[dict[str, Any]]],
) -> None:
    broken, healthy = two_tables
    broken_alice, broken_bob = broken.open("alice"), broken.open("bob")
    healthy_alice = healthy.open("alice")
    for connection in (broken_alice, broken_bob, healthy_alice):
        connection.outbox.drain()

    def defect(*arguments: object, **keywords: object) -> None:
        raise RuntimeError("an injected defect")

    monkeypatch.setattr(broken.session, "start_game", defect)
    broken.execute(broken_alice, decode.StartGame(request_id="a-02", expected_revision=2))

    assert broken.runtime.failed is True
    assert broken.failures == ["the table failed"], "the directory is told exactly once"
    for connection in (broken_alice, broken_bob):
        frames = connection.outbox.drain()
        assert [frame.message.type for frame in frames] == ["table_failed"]
        assert [frame.close_code for frame in frames] == [CLOSE_TABLE_FAILED]
        assert connection.stopped is True
    assert broken.runtime.connections == ()
    assert broken.runtime.authenticate(broken.credentials["alice"]) is None
    assert broken.scheduler.is_armed is False

    healthy.execute(healthy_alice, decode.StartGame(request_id="a-02", expected_revision=2))

    assert healthy.runtime.failed is False
    assert healthy.runtime.revision == 3
    assert [message["type"] for message in messages_of(healthy_alice)] == ["snapshot", "accepted"]


def test_a_failed_table_executes_nothing_more(
    two_tables: tuple[Harness, Harness],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broken, _ = two_tables
    alice = broken.open("alice")

    def defect(*arguments: object, **keywords: object) -> None:
        raise RuntimeError("an injected defect")

    monkeypatch.setattr(broken.session, "start_game", defect)
    broken.execute(alice, decode.StartGame(request_id="a-02", expected_revision=2))
    revision = broken.runtime.revision
    alice.outbox.drain()

    broken.execute(alice, decode.SitOut(request_id="a-03", expected_revision=revision))
    broken.runtime.fire_next_hand(revision)
    reconnected = broken.runtime.new_connection(broken.credentials["bob"], broken.user_ids["bob"])
    broken.runtime.connect(reconnected)

    assert broken.runtime.join(DisplayName("Carol"), 3) is None
    assert broken.runtime.revision == revision
    assert alice.outbox.drain() == []
    assert reconnected.outbox.drain() == []
    assert broken.failures == ["the table failed"], "on_failed fires once, not once per operation"


# --- Phase 1 never awaits (ADR 0008 §3, §4) ---


def _async_constructs(source: str) -> list[str]:
    """Every `await`, `async def`, `async for` and `async with` in a module's code."""
    return [type(node).__name__ for node in ast.walk(ast.parse(source)) if isinstance(node, ASYNC_NODES)]


def test_the_scan_detects_a_planted_await() -> None:
    assert _async_constructs("async def f():\n    await g()\n") == ["AsyncFunctionDef", "Await"]
    assert _async_constructs("def f():\n    return 1\n") == []


@pytest.mark.parametrize("path", PHASE_ONE_MODULES, ids=lambda path: path.name)
def test_a_phase_one_module_contains_no_await_and_no_async_def(path: Path) -> None:
    found = _async_constructs(path.read_text(encoding="utf-8"))
    assert found == [], f"{path.name} contains {found}: phase 1 must complete with no await"
