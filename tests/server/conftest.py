"""Server test helpers, exposed as fixtures because test modules cannot import each other.

Three groups:

- **the canonical fixtures** (`fixture_json`, `scenario_setup`): read from the repository path
  `docs/adr/0009-wire-protocol-v1/`, never copied. They are a read-only input of this Cycle.
- **real table state** (`parse_cards`, `queue_decks`, `make_table`, `join_table`, `member_user_id`): a real
  `TableSession` over the real engine, with the deck stacked through `Deck`'s own `_rng` shuffle seam, exactly as
  `tests/app/conftest.py` does. No double of the engine or of `app/` exists anywhere in these tests.
- **the leak checker** (`leak_check`, `identity_texts`): the per-viewer check of ADR 0005's Consequences, reusable on
  every server message a later step emits.
- **the invariant checkers** (`snapshot_invariants`, `snapshot_follows`): the structural, chip-conservation and
  per-connection-order checks of ADR 0009 §9 and §10, which are the fixtures' own regeneration checks re-derived from
  the server's messages. `tests/server/test_invariant_checkers.py` proves each of them can fail.
"""

import asyncio
import faulthandler
import json
from collections.abc import Callable, Iterable, Iterator, Mapping, MutableSequence, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from random import Random
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from go_poker.app.identity import DisplayName, UserId
from go_poker.app.results import Accepted, CommandResult
from go_poker.app.session import TableSession
from go_poker.core.card import Card, Rank, Suit
from go_poker.core.deck import Deck
from go_poker.game.game_lifecycle import ButtonChooser
from go_poker.game.variants.texas_holdem.dealing import HOLE_CARD_COUNT
from go_poker.server import decode
from go_poker.server.app import create_app
from go_poker.server.config import ServerConfig
from go_poker.server.directory import TableDirectory
from go_poker.server.runtime import Connection, JoinedMember, TableRuntime

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0009-wire-protocol-v1"

# The engine's own shuffle, captured before any test patches it, so `queue_decks` can be used more than once.
_DECK_SHUFFLE = Deck.shuffle

# The longest any one server test may run before the process dumps every thread's stack and exits non-zero. A test
# that blocks (a `receive_json()` waiting for a message that never comes) would otherwise hang the suite until the
# CI job's own timeout. It is generous: the whole `tests/server/` suite runs in seconds. It uses the standard
# library's `faulthandler` rather than `pytest-timeout`, which would be a new dependency.
TEST_HANG_LIMIT_SECONDS = 60


@pytest.fixture(autouse=True)
def fail_a_hung_test() -> Iterator[None]:
    """Turn a hung server test into a stack dump of every thread and a non-zero exit, instead of a silent hang."""
    faulthandler.dump_traceback_later(TEST_HANG_LIMIT_SECONDS, exit=True)
    yield
    faulthandler.cancel_dump_traceback_later()


RANKS: Mapping[str, Rank] = {
    "2": Rank.TWO,
    "3": Rank.THREE,
    "4": Rank.FOUR,
    "5": Rank.FIVE,
    "6": Rank.SIX,
    "7": Rank.SEVEN,
    "8": Rank.EIGHT,
    "9": Rank.NINE,
    "T": Rank.TEN,
    "J": Rank.JACK,
    "Q": Rank.QUEEN,
    "K": Rank.KING,
    "A": Rank.ACE,
}
SUITS: Mapping[str, Suit] = {"c": Suit.CLUBS, "d": Suit.DIAMONDS, "h": Suit.HEARTS, "s": Suit.SPADES}

# The scenarios' button rules (`setup.button`).
BUTTON_CHOOSERS: Mapping[str, ButtonChooser] = {"lowest_starting_seat": min}


def _fixture_json(relative: str) -> Any:
    return json.loads((FIXTURE_ROOT / relative).read_text(encoding="utf-8"))


def _scenario_setup(name: str) -> Mapping[str, Any]:
    setup: Mapping[str, Any] = _fixture_json(f"scenarios/{name}.json")["setup"]
    return setup


def _parse_card(token: str) -> Card:
    """One card from its two wire characters, rank then suit (ADR 0009 §3)."""
    rank, suit = token
    return Card(RANKS[rank], SUITS[suit])


def _parse_cards(tokens: Iterable[str]) -> list[Card]:
    return [_parse_card(token) for token in tokens]


class StackedRandom(Random):
    """A shuffle that puts the given cards on top of the deck, so they are drawn first, in this order."""

    def __init__(self, draw_order: list[Card]) -> None:
        super().__init__()
        self._draw_order = draw_order

    def shuffle(self, x: MutableSequence[Any]) -> None:
        rest = [card for card in x if card not in self._draw_order]
        # draw() pops from the end, so the first card to draw goes last.
        x[:] = rest + list(reversed(self._draw_order))


class DeckQueue(Random):
    """A shuffle that stacks each new deck with the next queued draw order, one order per engine shuffle.

    A shuffle beyond the queued orders keeps the deck unshuffled, as the scenario format states.
    """

    def __init__(self, draw_orders: list[list[Card]]) -> None:
        super().__init__()
        self._pending = list(draw_orders)

    def shuffle(self, x: MutableSequence[Any]) -> None:
        if self._pending:
            StackedRandom(self._pending.pop(0)).shuffle(x)


def _member_user_id(name: str) -> UserId:
    """The `UserId` of a test member: distinctive text, so that a leak of it is easy to find."""
    return UserId(f"uid-{name}-7f3a")


def _display_name(name: str) -> DisplayName:
    """The display name of a test member, as the fixtures spell it: the capitalized actor name."""
    return DisplayName(name.capitalize())


def _server_config(setup: Mapping[str, Any]) -> ServerConfig:
    """The configuration a scenario's `setup` describes, with its ids and button rule injected into the seams."""
    defaults = setup["server_defaults"]
    identifiers = setup["ids"]
    return ServerConfig(
        small_blind=defaults["small_blind"],
        big_blind=defaults["big_blind"],
        buy_in=defaults["buy_in"],
        max_seats=defaults["max_seats"],
        host_seat=defaults["host_seat"],
        new_table_id=lambda: str(identifiers["table_id"]),
        new_join_code=lambda: str(identifiers["join_code"]),
        choose_button=BUTTON_CHOOSERS[setup["button"]],
    )


def _make_table(setup: Mapping[str, Any], host: str) -> tuple[TableSession, ServerConfig]:
    """A real `TableSession` created as the server creates one: the configured settings, ids and button chooser, with
    `host` seated at the configured host seat."""
    config = _server_config(setup)
    session = TableSession.create(
        config.new_table_id(),
        config.new_join_code(),
        config.settings,
        _member_user_id(host),
        _display_name(host),
        config.host_seat,
        choose_button=config.choose_button,
    )
    return session, config


def _accepted(result: CommandResult) -> Accepted:
    assert isinstance(result, Accepted), f"expected an accepted command, got {result}"
    return result


def _join_table(session: TableSession, name: str, seat: int) -> Accepted:
    """Join as the server joins (ADR 0009 §4, C6.1 E4): with the table's current revision."""
    return _accepted(session.join(_member_user_id(name), session.revision, _display_name(name), seat))


def _identity_texts(setup: Mapping[str, Any]) -> list[str]:
    """Every text that must never appear in a server message: the members' user ids, their credentials, and the names
    of the identity fields the protocol never carries (ADR 0009 §2)."""
    credentials: Mapping[str, str] = setup["ids"]["credentials"]
    return [
        *(_member_user_id(name).value for name in credentials),
        *credentials.values(),
        "player_id",
        "user_id",
    ]


def _strings(node: object) -> Iterator[str]:
    """Every string in a parsed JSON value, keys included."""
    if isinstance(node, Mapping):
        for key, value in node.items():
            yield str(key)
            yield from _strings(value)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _strings(item)
    elif isinstance(node, str):
        yield node


def _shown_seats(hand: Mapping[str, Any]) -> set[int]:
    """The seats whose cards everyone may see, read from the message itself: every seat of an all-in showdown, and
    each seat that decided to show in an interactive one."""
    showdown = hand["showdown"]
    if showdown is None:
        return set()
    if showdown["kind"] == "all_in":
        return set(showdown["order"])
    return {decision["seat"] for decision in showdown["decisions"] if decision["decision"] == "show"}


def _assert_no_card_leak(snapshot: Mapping[str, Any]) -> None:
    """No card value outside the viewer's own seat and the shown seats, and the card backs instead of them."""
    view = snapshot["view"]
    hand = view["hand"]
    if hand is None:
        return
    viewer = view["you"]["seat"]
    shown = _shown_seats(hand)
    visible = shown | {viewer}
    for participant in hand["participants"]:
        if participant["seat"] in visible:
            continue
        seat = participant["seat"]
        assert participant["hole_cards"] is None, f"seat {seat}'s cards reached seat {viewer}"
        assert participant["strength"] is None, f"seat {seat}'s strength reached seat {viewer}"
        expected_backs = HOLE_CARD_COUNT if participant["has_live_cards"] else 0
        assert participant["hidden_card_count"] == expected_backs
    for shown_rank in (hand["settlement"] or {"shown_ranks": []})["shown_ranks"]:
        assert shown_rank["seat"] in shown, "a settlement rank of a seat that did not show"
    own = next((each for each in hand["participants"] if each["seat"] == viewer), None)
    for event in hand["log"]:
        if event["event"] == "hole_cards_dealt" and event["own_cards"] is not None:
            assert own is not None and own["hole_cards"] == event["own_cards"], "the log dealt cards of another seat"


def _leak_check(message: Mapping[str, Any], forbidden: Sequence[str]) -> None:
    """Every leak check for one serialized server message: no identity text anywhere, and, for a snapshot, no card
    outside the viewer's own seat and the shown seats."""
    for text in _strings(message):
        for secret in forbidden:
            assert secret not in text, f"{secret!r} leaked into a {message['type']} message"
    if message["type"] == "snapshot":
        _assert_no_card_leak(message)


# --- The view and chip invariants of every emitted snapshot (ADR 0009 §10, §11; the fixtures' README checks) ---

# The whole-number of cards a hidden live hand is drawn as, which is the engine's own constant.
BACKS_FOR_A_LIVE_HIDDEN_HAND = HOLE_CARD_COUNT
# The engine evaluates a hand's strength once the board can make five cards with two hole cards.
BOARD_CARDS_BEFORE_A_STRENGTH = 3


@dataclass(frozen=True)
class InvariantCounts:
    """How many checks one invariant run really made, so a test can prove it was not vacuous."""

    hands: int = 0
    settled: int = 0

    def __add__(self, other: InvariantCounts) -> InvariantCounts:
        return InvariantCounts(hands=self.hands + other.hands, settled=self.settled + other.settled)


def _committed_by_seat(log: Sequence[Mapping[str, Any]]) -> dict[int, int]:
    """Each seat's net chips committed to the pots this hand, read from the redacted log alone (ADR 0009 §10).

    A posted blind and an action add chips; a returned uncalled bet takes them back.
    """
    committed: dict[int, int] = {}
    for event in log:
        match event["event"]:
            case "blinds_posted":
                for post in event["posts"]:
                    committed[post["seat"]] = committed.get(post["seat"], 0) + post["chips"]
            case "action_taken":
                committed[event["seat"]] = committed.get(event["seat"], 0) + event["chips"]
            case "chips_returned":
                committed[event["seat"]] = committed.get(event["seat"], 0) - event["chips"]
            case _:
                continue
    return committed


def _starting_stacks(log: Sequence[Mapping[str, Any]]) -> dict[int, int]:
    """The stack each participant started the hand with, from the `hand_started` event."""
    for event in log:
        if event["event"] == "hand_started":
            return {each["seat"]: each["starting_stack"] for each in event["participants"]}
    raise AssertionError("a hand's log always starts with hand_started")


def _assert_turn_scoped(hand: Mapping[str, Any], viewer: int) -> None:
    """`legal_actions` and `showdown_actions` exist exactly in the view of the one seat that must act now."""
    turn = hand["turn"]
    must_bet = turn is not None and turn["kind"] == "betting" and turn["seat"] == viewer
    must_decide = turn is not None and turn["kind"] == "showdown" and turn["seat"] == viewer
    assert (hand["legal_actions"] is not None) == must_bet, f"legal_actions of seat {viewer} with turn {turn}"
    assert (hand["showdown_actions"] is not None) == must_decide, f"showdown_actions of seat {viewer}, turn {turn}"
    if hand["showdown_actions"] is not None:
        assert hand["showdown_actions"] == ["show", "muck"], hand["showdown_actions"]


def _assert_card_counts(hand: Mapping[str, Any]) -> None:
    """`hidden_card_count` agrees with `hole_cards` and `has_live_cards` for **every** seat, and a strength exists
    exactly where the viewer sees the cards and the board can make five (ADR 0009 §10)."""
    board = len(hand["board"])
    for participant in hand["participants"]:
        seen = participant["hole_cards"] is not None
        expected = 0 if seen or not participant["has_live_cards"] else BACKS_FOR_A_LIVE_HIDDEN_HAND
        assert participant["hidden_card_count"] == expected, f"seat {participant['seat']}: {participant}"
        if seen:
            assert len(participant["hole_cards"]) == BACKS_FOR_A_LIVE_HIDDEN_HAND, participant
        has_strength = participant["strength"] is not None
        assert has_strength == (seen and board >= BOARD_CARDS_BEFORE_A_STRENGTH), participant
        if has_strength:
            assert len(participant["strength"]["cards"]) == 5, participant


def _assert_pots(hand: Mapping[str, Any]) -> None:
    """Every pot layer is a positive amount with a non-empty ascending eligible-seat list (ADR 0009 §10)."""
    participants = {each["seat"] for each in hand["participants"]}
    for pot in hand["pots"]:
        assert pot["amount"] >= 1, pot
        assert pot["eligible_seats"] == sorted(pot["eligible_seats"]), pot
        assert pot["eligible_seats"], pot
        assert set(pot["eligible_seats"]) <= participants, pot


def _assert_chips_are_conserved(view: Mapping[str, Any], hand: Mapping[str, Any]) -> bool:
    """Chip conservation for one snapshot, from the view alone. Returns whether the hand was settled.

    While a hand runs, every chip of a participant is behind, in front, or in a pot. Once it is settled, the pots are
    still displayed but the chips are back in the stacks, so the awards are what has to add up: the pots equal the
    collected contributions, each award's shares add up to it, every winner is eligible, and each participant's stack
    is its starting stack minus what it committed plus what it won.
    """
    log = hand["log"]
    starting = _starting_stacks(log)
    committed = _committed_by_seat(log)
    seats = [each["seat"] for each in hand["participants"]]
    assert set(seats) == set(starting), f"the participants are the seats the hand started with: {seats}, {starting}"
    stacks = {seat["seat"]: (seat["occupant"] or {}).get("stack") for seat in view["seats"]}
    seated = all(stacks.get(seat) is not None for seat in seats)
    pots = sum(pot["amount"] for pot in hand["pots"])
    settlement = hand["settlement"]

    if settlement is None:
        in_front = sum(each["in_front"] for each in hand["participants"])
        assert pots + in_front == sum(committed.values()), f"pots {pots} + in front {in_front} != {committed}"
        if seated:
            behind = sum(int(stacks[seat]) for seat in seats)
            assert behind + in_front + pots == sum(starting.values()), (
                f"behind {behind} + in front {in_front} + pots {pots} != {sum(starting.values())}"
            )
        return False

    awarded: dict[int, int] = {}
    for award in settlement["pot_awards"]:
        assert sum(share["amount"] for share in award["shares"]) == award["amount"], award
        for share in award["shares"]:
            assert share["seat"] in award["eligible_seats"], f"an award to a seat that was not eligible: {award}"
            awarded[share["seat"]] = awarded.get(share["seat"], 0) + share["amount"]
    total_awards = sum(award["amount"] for award in settlement["pot_awards"])
    assert total_awards == pots, f"the awards {total_awards} are not the pots {pots}"
    assert total_awards == sum(committed.values()), f"the awards {total_awards} are not the contributions {committed}"
    if seated:
        for seat in seats:
            expected = starting[seat] - committed.get(seat, 0) + awarded.get(seat, 0)
            assert stacks[seat] == expected, f"seat {seat} holds {stacks[seat]}, not {expected}"
        assert sum(int(stacks[seat]) for seat in seats) == sum(starting.values()), "chips were created or destroyed"
    return True


def _snapshot_invariants(message: Mapping[str, Any]) -> InvariantCounts:
    """Every structural and chip invariant of one emitted snapshot, beyond the per-viewer leak check."""
    assert message["type"] == "snapshot", message["type"]
    view = message["view"]
    max_seats = view["settings"]["max_seats"]
    assert [seat["seat"] for seat in view["seats"]] == list(range(1, max_seats + 1)), "seats 1..max_seats, ascending"
    hand = view["hand"]
    if hand is None:
        return InvariantCounts()
    viewer = view["you"]["seat"]
    _assert_turn_scoped(hand, viewer)
    _assert_card_counts(hand)
    _assert_pots(hand)
    settled = _assert_chips_are_conserved(view, hand)
    return InvariantCounts(hands=1, settled=1 if settled else 0)


# The `you` fields a member's private intents live in, and the only ones two snapshots at one revision may differ
# in (ADR 0006 §4, ADR 0009 §9.3).
PRIVATE_YOU_FIELDS = ("pending_leave", "pending_sit_out", "pre_action", "pre_action_options")


def _without_private_intents(view: Mapping[str, Any]) -> dict[str, Any]:
    """A view with the viewer's own private intents removed, which is the shared state it carries."""
    shared = dict(view)
    shared["you"] = {key: value for key, value in view["you"].items() if key not in PRIVATE_YOU_FIELDS}
    return shared


def _assert_snapshot_follows(previous: Mapping[str, Any] | None, snapshot: Mapping[str, Any]) -> None:
    """What one connection's next snapshot may be (ADR 0009 §9.1, §9.3).

    Revisions never decrease, and two snapshots at the same revision differ only in that member's private intents.
    """
    if previous is None:
        return
    assert snapshot["revision"] >= previous["revision"], (
        f"a revision went backwards: {previous['revision']} then {snapshot['revision']}"
    )
    if snapshot["revision"] == previous["revision"]:
        assert _without_private_intents(previous["view"]) == _without_private_intents(snapshot["view"]), (
            f"two snapshots at revision {snapshot['revision']} differ outside the private `you` fields"
        )


@pytest.fixture
def snapshot_invariants() -> Callable[[Mapping[str, Any]], InvariantCounts]:
    """Check one emitted snapshot's view and chip invariants, and report how many checks it made."""
    return _snapshot_invariants


@pytest.fixture
def snapshot_follows() -> Callable[[Mapping[str, Any] | None, Mapping[str, Any]], None]:
    """Check one connection's snapshot against the previous one it received (ADR 0009 §9.1, §9.3)."""
    return _assert_snapshot_follows


@pytest.fixture
def no_counts() -> InvariantCounts:
    """The empty accumulator for `snapshot_invariants`, so a test module needs no import from here."""
    return InvariantCounts()


@pytest.fixture
def fixture_json() -> Callable[[str], Any]:
    """Read one canonical fixture, by its path under `docs/adr/0009-wire-protocol-v1/`."""
    return _fixture_json


@pytest.fixture
def scenario_setup() -> Callable[[str], Mapping[str, Any]]:
    """The `setup` of one canonical scenario, by name."""
    return _scenario_setup


@pytest.fixture
def parse_cards() -> Callable[[Iterable[str]], list[Card]]:
    """Parse a scenario's `"Qs"`-style card strings into engine cards, in the order given."""
    return _parse_cards


@pytest.fixture
def queue_decks(monkeypatch: pytest.MonkeyPatch) -> Callable[..., DeckQueue]:
    """Queue one stacked draw order per engine shuffle, through `Deck`'s own `_rng` seam.

    It may be called again to start a fresh queue, for a test that replays several scenarios: the patch always
    delegates to the pristine `Deck.shuffle` captured at import, never to a previous patch.
    """

    def queue(*draw_orders: list[Card]) -> DeckQueue:
        rng = DeckQueue(list(draw_orders))
        monkeypatch.setattr(Deck, "shuffle", lambda deck, *, _rng=None: _DECK_SHUFFLE(deck, _rng=rng))
        return rng

    return queue


@pytest.fixture
def member_user_id() -> Callable[[str], UserId]:
    return _member_user_id


@pytest.fixture
def make_table() -> Callable[[Mapping[str, Any], str], tuple[TableSession, ServerConfig]]:
    return _make_table


@pytest.fixture
def join_table() -> Callable[[TableSession, str, int], Accepted]:
    return _join_table


@pytest.fixture
def accepted() -> Callable[[CommandResult], Accepted]:
    return _accepted


@pytest.fixture
def identity_texts() -> Callable[[Mapping[str, Any]], list[str]]:
    return _identity_texts


@pytest.fixture
def leak_check() -> Callable[[Mapping[str, Any], Sequence[str]], None]:
    return _leak_check


# --- The runtime harness: a real session and real connections, with no socket and no double of the engine ---


class ManualNextHandScheduler:
    """The next-hand pause under the test's control (the `server_timer` step of a scenario).

    It is the test's scheduler, never production's: arming replaces any armed call, and `fire` is one-shot, like the
    `call_later` handle the production scheduler holds.
    """

    def __init__(self) -> None:
        self.armed: tuple[float, Callable[[], None]] | None = None
        self.cancellations = 0

    def arm(self, delay: float, fire: Callable[[], None]) -> None:
        self.armed = (delay, fire)

    def cancel(self) -> None:
        self.armed = None
        self.cancellations += 1

    @property
    def is_armed(self) -> bool:
        return self.armed is not None

    @property
    def delay(self) -> float:
        assert self.armed is not None, "nothing is armed"
        return self.armed[0]

    def armed_call(self) -> Callable[[], None]:
        """The call the scheduler would make, so that a test can keep a stale one and fire it later."""
        assert self.armed is not None, "nothing is armed"
        return self.armed[1]

    def fire(self) -> None:
        armed = self.armed
        assert armed is not None, "nothing is armed"
        self.armed = None
        armed[1]()


@dataclass
class RuntimeHarness:
    """One table's runtime with its real session, plus the identities and connections a test drives it through."""

    runtime: TableRuntime
    session: TableSession
    config: ServerConfig
    scheduler: ManualNextHandScheduler
    failures: list[str]
    user_ids: dict[str, UserId]
    credentials: dict[str, str]

    def join(self, name: str, seat: int) -> JoinedMember:
        """The HTTP join, through the runtime, recording the identity it minted."""
        joined = self.runtime.join(_display_name(name), seat)
        assert isinstance(joined, JoinedMember), f"the join was not accepted: {joined}"
        self.user_ids[name] = joined.user_id
        self.credentials[name] = joined.credential
        return joined

    def open(self, name: str) -> Connection:
        """A new connection of a member, authenticated as the WebSocket would and registered by the runtime."""
        credential = self.credentials[name]
        user_id = self.runtime.authenticate(credential)
        assert user_id == self.user_ids[name], "the credential must authenticate as this member"
        connection = self.runtime.new_connection(credential, user_id)
        self.runtime.connect(connection)
        return connection

    def execute(self, connection: Connection, command: decode.Command) -> None:
        self.runtime.execute(command, connection)

    def identity_texts(self) -> list[str]:
        """The texts no server message of this table may contain (ADR 0009 §2)."""
        return [
            *(user_id.value for user_id in self.user_ids.values()),
            *self.credentials.values(),
            "player_id",
            "user_id",
        ]


def _make_runtime(setup: Mapping[str, Any], host: str, **overrides: Any) -> RuntimeHarness:
    """A `TableRuntime` over a real `TableSession` created from a scenario's `setup`, with the host already a member.

    `overrides` replace `ServerConfig` fields (`outbox_size` in the overflow tests). The host's credential is the
    scenario's; a later joiner's identity and credential come from the configured generators, as in production.
    """
    session, config = _make_table(setup, host)
    scheduler = ManualNextHandScheduler()
    config = replace(config, new_next_hand_scheduler=lambda: scheduler, **overrides)
    host_credential: str = setup["ids"]["credentials"][host]
    failures: list[str] = []
    runtime = TableRuntime(
        session,
        config,
        {host_credential: _member_user_id(host)},
        table_id=config.new_table_id(),
        join_code=config.new_join_code(),
        on_failed=lambda: failures.append("the table failed"),
    )
    return RuntimeHarness(
        runtime=runtime,
        session=session,
        config=config,
        scheduler=scheduler,
        failures=failures,
        user_ids={host: _member_user_id(host)},
        credentials={host: host_credential},
    )


def _messages_of(connection: Connection) -> list[dict[str, Any]]:
    """Every queued frame of a connection as serialized JSON, draining it, with the `message` fields dropped."""
    return [_without_messages(frame.message.model_dump(mode="json")) for frame in connection.outbox.drain()]


def _without_messages(value: Any) -> Any:
    """A parsed JSON value with every diagnostic `message` field dropped (ADR 0009 §15: conformance ignores them)."""
    if isinstance(value, Mapping):
        return {key: _without_messages(item) for key, item in value.items() if key != "message"}
    if isinstance(value, list):
        return [_without_messages(item) for item in value]
    return value


@pytest.fixture
def make_runtime() -> Callable[..., RuntimeHarness]:
    return _make_runtime


@pytest.fixture
def messages_of() -> Callable[[Connection], list[dict[str, Any]]]:
    return _messages_of


@pytest.fixture
def without_messages() -> Callable[[Any], Any]:
    return _without_messages


# --- The app harness: the real FastAPI application, with only the scenarios' own seams injected ---

# Long enough for the loop thread to hand a pending send to the test session, short enough to stay fast.
SETTLE_SECONDS = 0.02


def _minting_user_ids(recorded: list[str]) -> Callable[[], UserId]:
    """A user-id generator whose values are distinctive, so that a leak of one is easy to find, and recorded."""

    def mint() -> UserId:
        value = f"uid-{len(recorded) + 1}-7f3a"
        recorded.append(value)
        return UserId(value)

    return mint


def _recording_schedulers(recorded: list[ManualNextHandScheduler]) -> Callable[[], ManualNextHandScheduler]:
    def new() -> ManualNextHandScheduler:
        scheduler = ManualNextHandScheduler()
        recorded.append(scheduler)
        return scheduler

    return new


def _sequence(values: Sequence[str], what: str) -> Callable[[], str]:
    """A generator handing out exactly these values, in order, and failing loudly when they run out."""
    remaining = iter(list(values))

    def next_value() -> str:
        try:
            return next(remaining)
        except StopIteration:
            raise AssertionError(f"the scenario ran out of {what}") from None

    return next_value


@dataclass
class AppHarness:
    """The real application under test, with the seams a scenario needs and a record of what they handed out."""

    app: FastAPI
    config: ServerConfig
    schedulers: list[ManualNextHandScheduler]
    minted_user_ids: list[str]
    credentials: list[str]

    @property
    def directory(self) -> TableDirectory:
        directory = self.app.state.directory
        assert isinstance(directory, TableDirectory)
        return directory

    def identity_texts(self, *extra: str) -> list[str]:
        """The texts no server message may contain (ADR 0009 §2)."""
        return [*self.minted_user_ids, *self.credentials, *extra, "player_id", "user_id"]

    def armed_scheduler(self) -> ManualNextHandScheduler:
        armed = [scheduler for scheduler in self.schedulers if scheduler.is_armed]
        assert len(armed) == 1, f"expected exactly one armed next-hand call, found {len(armed)}"
        return armed[0]


def _make_app(**overrides: Any) -> AppHarness:
    """The real `create_app`, with the user-id generator and the next-hand scheduler recorded.

    `overrides` are `ServerConfig` fields. Nothing else is replaced: the directory, the runtime, the session and the
    engine are the production ones.
    """
    minted: list[str] = []
    schedulers: list[ManualNextHandScheduler] = []
    config = ServerConfig(
        new_user_id=_minting_user_ids(minted),
        new_next_hand_scheduler=_recording_schedulers(schedulers),
        **overrides,
    )
    return AppHarness(
        app=create_app(config), config=config, schedulers=schedulers, minted_user_ids=minted, credentials=[]
    )


def _membership_credentials(scenario: Mapping[str, Any]) -> list[str]:
    """The scenario's credentials in the order the memberships are created: the host's, then one per accepted join.

    The order is read from the scenario's own HTTP steps, so the actor-keyed `ids.credentials` needs no assumption
    about key order.
    """
    credentials: Mapping[str, str] = scenario["setup"]["ids"]["credentials"]
    return [
        credentials[step["actor"]]
        for step in scenario["steps"]
        if step["op"] == "http" and 200 <= step["response"]["status"] < 300
    ]


def _scenario_app(scenario: Mapping[str, Any]) -> AppHarness:
    """An application built from a scenario's `setup` alone (C6.4 Brief §6.1)."""
    setup = scenario["setup"]
    defaults = setup["server_defaults"]
    identifiers = setup["ids"]
    credentials = _membership_credentials(scenario)
    harness = _make_app(
        small_blind=defaults["small_blind"],
        big_blind=defaults["big_blind"],
        buy_in=defaults["buy_in"],
        max_seats=defaults["max_seats"],
        host_seat=defaults["host_seat"],
        new_table_id=_sequence([identifiers["table_id"]], "table ids"),
        new_join_code=_sequence([identifiers["join_code"]], "join codes"),
        new_credential=_sequence(credentials, "credentials"),
        choose_button=BUTTON_CHOOSERS[setup["button"]],
    )
    harness.credentials.extend(credentials)
    return harness


async def _settle() -> None:
    """Let the event loop hand every pending send to the test sessions."""
    await asyncio.sleep(SETTLE_SECONDS)


def _pending_frames(session: WebSocketTestSession) -> int:
    """How many frames the application has sent this connection that the test has not read.

    Starlette's test session buffers them in the receive end of its own memory stream, and offers no public way to
    ask "is anything queued?". The harness needs exactly that, to prove a connection received nothing beyond its
    scenario's `receive` steps, so it reads the buffer's statistics here and nowhere else.
    """
    return int(session._send_rx.statistics().current_buffer_used)  # noqa: SLF001


def _assert_nothing_pending(client: TestClient, sessions: Mapping[str, WebSocketTestSession]) -> None:
    """Each connection received exactly its scenario's `receive` steps, in that order, and nothing else."""
    client.portal.call(_settle)
    for name, session in sessions.items():
        pending = _pending_frames(session)
        assert pending == 0, f"{name} received {pending} message(s) its scenario does not list"


def _drain_socket(client: TestClient, session: WebSocketTestSession) -> list[Any]:
    """Every message the application has already sent this connection, in order, leaving nothing pending.

    It settles the loop first, so a send in flight is counted. A pending close raises `WebSocketDisconnect`, which a
    test expecting a close catches itself.
    """
    client.portal.call(_settle)
    messages: list[Any] = []
    while _pending_frames(session) > 0:
        messages.append(session.receive_json())
    return messages


def _fire_next_hand(client: TestClient, harness: AppHarness) -> None:
    """A scenario's `server_timer` step: fire the armed next-hand call inside the event loop.

    The armed call is synchronous phase 1, so it must run on the loop thread, never on the test thread.
    """
    scheduler = harness.armed_scheduler()

    async def fire() -> None:
        scheduler.fire()

    client.portal.call(fire)


def _inject_defect(monkeypatch: pytest.MonkeyPatch, runtime: TableRuntime, command: str) -> None:
    """Make one table's own `TableSession` raise from one command, which is a defect inside phase 1.

    It reaches the runtime's session through the same private access `tests/app/conftest.py` uses: a defect has to
    come from inside the table, and no production code exposes the session.
    """

    def defect(*arguments: object, **keywords: object) -> None:
        raise RuntimeError("an injected defect")

    monkeypatch.setattr(runtime._session, command, defect)  # noqa: SLF001


@pytest.fixture
def make_app() -> Callable[..., AppHarness]:
    return _make_app


@pytest.fixture
def scenario_app() -> Callable[[Mapping[str, Any]], AppHarness]:
    return _scenario_app


@pytest.fixture
def assert_nothing_pending() -> Callable[[TestClient, Mapping[str, WebSocketTestSession]], None]:
    return _assert_nothing_pending


@pytest.fixture
def fire_next_hand() -> Callable[[TestClient, AppHarness], None]:
    return _fire_next_hand


@pytest.fixture
def drain_socket() -> Callable[[TestClient, WebSocketTestSession], list[Any]]:
    return _drain_socket


@pytest.fixture
def inject_defect() -> Callable[[pytest.MonkeyPatch, TableRuntime, str], None]:
    return _inject_defect
