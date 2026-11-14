"""The conformance test: every canonical scenario replayed through the real server (ADR 0009 §15).

Each scenario is driven with FastAPI's `TestClient` over the real app, the real `TableRuntime`, the real
`TableSession` and the real engine. The only injected seams are the ones the scenario itself states: its ids, its
button rule, its stacked draw orders, and the next-hand trigger.

`TestClient` is entered as a context manager on purpose: that gives every `websocket_connect` of one client the same
blocking portal, and therefore one event loop, which the app's events and tasks belong to.
"""

import json
from contextlib import ExitStack
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from go_poker.core.card import Card, Rank, Suit
from go_poker.core.deck import Deck
from go_poker.server import dto
from go_poker.server.runtime import Frame

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0009-wire-protocol-v1"
SCENARIOS = sorted((FIXTURE_ROOT / "scenarios").glob("*.json"))
SERVER_MESSAGES = sorted((FIXTURE_ROOT / "messages" / "server").glob("*.json"))

# The two fixtures no scenario produces (the fixtures' README): nine seats needs its own table, and no engine path
# produces a defect. Each has its own focused test below.
UNCOVERED_BY_SCENARIOS = frozenset({"snapshot.nine_seats.actor.json", "table_failed.json"})

# An abrupt loss with no close handshake, which is what a `drop` step means.
ABNORMAL_CLOSURE = 1006

NINE_SEAT_NAMES = ("Alice", "Bob", "Carol", "Dave", "Erin", "Frank", "Zoë", "Alexandrina-Montague", "Ivan")
EIGHT_OF_HEARTS = Card(Rank.EIGHT, Suit.HEARTS)
NINE_OF_SPADES = Card(Rank.NINE, Suit.SPADES)


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _replay(
    scenario: Any,
    *,
    scenario_app: Any,
    queue_decks: Any,
    parse_cards: Any,
    without_messages: Any,
    leak_check: Any,
    snapshot_invariants: Any,
    snapshot_follows: Any,
    assert_nothing_pending: Any,
    fire_next_hand: Any,
) -> list[Any]:
    """Drive one scenario end to end and return every message its connections received.

    Every step kind of the fixtures' scenario format is handled here, and an unknown one fails the test.
    """
    harness = scenario_app(scenario)
    queue_decks(*(parse_cards(hand["draw_order"]) for hand in scenario["setup"]["hands"]))
    received: list[Any] = []
    sessions: dict[str, WebSocketTestSession] = {}
    dropped: set[str] = set()
    # The last snapshot each connection received, for the per-connection order of ADR 0009 §9.1 and §9.3.
    latest: dict[str, Any] = {}

    with TestClient(harness.app) as client, ExitStack() as connections:
        for step in scenario["steps"]:
            operation = step["op"]
            if operation == "http":
                request, expected = step["request"], step["response"]
                assert request["method"] == "POST"
                response = client.post(request["path"], json=request["body"])
                assert response.status_code == expected["status"], step
                assert without_messages(response.json()) == without_messages(expected["body"]), step
                assert response.headers["cache-control"] == "no-store"
            elif operation == "open":
                sessions[step["connection"]] = connections.enter_context(client.websocket_connect(step["path"]))
            elif operation == "send":
                session = sessions[step["connection"]]
                if "raw" in step:
                    session.send_text(step["raw"])
                else:
                    session.send_json(step["message"])
            elif operation == "receive":
                message = sessions[step["connection"]].receive_json()
                assert without_messages(message) == without_messages(step["message"]), step
                # Brief §6.4: no identity text in *any* server message, not only in a snapshot.
                leak_check(message, harness.identity_texts())
                if message["type"] == "snapshot":
                    snapshot_invariants(message)
                    snapshot_follows(latest.get(step["connection"]), message)
                    latest[step["connection"]] = message
                received.append(message)
            elif operation == "server_close":
                with pytest.raises(WebSocketDisconnect) as closed:
                    sessions[step["connection"]].receive_json()
                assert closed.value.code == step["code"], step
            elif operation == "drop":
                sessions[step["connection"]].send({"type": "websocket.disconnect", "code": ABNORMAL_CLOSURE})
                dropped.add(step["connection"])
            elif operation == "server_timer":
                assert step["timer"] == "next_hand"
                fire_next_hand(client, harness)
            elif operation == "note":
                continue
            else:
                pytest.fail(f"unknown scenario step {operation!r}")

        # A dropped connection is exempt: its queued frames go into a closed socket by definition.
        assert_nothing_pending(client, {name: s for name, s in sessions.items() if name not in dropped})
    return received


@pytest.fixture
def replay(
    scenario_app: Any,
    queue_decks: Any,
    parse_cards: Any,
    without_messages: Any,
    leak_check: Any,
    snapshot_invariants: Any,
    snapshot_follows: Any,
    assert_nothing_pending: Any,
    fire_next_hand: Any,
) -> Any:
    def run(scenario: Any) -> list[Any]:
        return _replay(
            scenario,
            scenario_app=scenario_app,
            queue_decks=queue_decks,
            parse_cards=parse_cards,
            without_messages=without_messages,
            leak_check=leak_check,
            snapshot_invariants=snapshot_invariants,
            snapshot_follows=snapshot_follows,
            assert_nothing_pending=assert_nothing_pending,
            fire_next_hand=fire_next_hand,
        )

    return run


def test_the_scenarios_are_where_this_test_expects_them() -> None:
    assert len(SCENARIOS) == 8
    assert len(SERVER_MESSAGES) >= 30


@pytest.mark.parametrize("path", SCENARIOS, ids=lambda path: path.stem)
def test_a_canonical_scenario_replays_exactly(path: Path, replay: Any) -> None:
    received = replay(_load(path))
    assert received, "a scenario with no received message proves nothing"


def test_every_server_message_fixture_appears_in_a_replay(replay: Any, without_messages: Any) -> None:
    """Brief §6.2: every `messages/server/*.json` appears in a scenario replay, except the two with focused tests."""
    seen = [without_messages(message) for path in SCENARIOS for message in replay(_load(path))]
    uncovered = {path.name for path in SERVER_MESSAGES if without_messages(_load(path)) not in seen}
    assert uncovered == UNCOVERED_BY_SCENARIOS


def test_the_quiet_check_catches_an_extra_message(
    scenario_app: Any,
    queue_decks: Any,
    parse_cards: Any,
    assert_nothing_pending: Any,
) -> None:
    """The end-of-scenario check must be able to fail, or it proves nothing."""
    scenario = _load(FIXTURE_ROOT / "scenarios" / "pre_action_private.json")
    harness = scenario_app(scenario)
    queue_decks(*(parse_cards(hand["draw_order"]) for hand in scenario["setup"]["hands"]))
    setup = scenario["setup"]

    with TestClient(harness.app) as client:
        client.post("/tables", json={"display_name": "Alice"})
        path = f"/ws/tables/{setup['ids']['table_id']}"
        with client.websocket_connect(path) as session:
            session.send_json(
                {
                    "type": "hello",
                    "protocol": "go-poker.v1",
                    "credential": setup["ids"]["credentials"]["alice"],
                }
            )
            session.receive_json()
            assert_nothing_pending(client, {"alice-1": session})

            runtime = harness.directory.get(setup["ids"]["table_id"])
            assert runtime is not None

            async def plant() -> None:
                runtime.connections[0].deliver(
                    Frame(dto.ErrorMessage(type="error", request_id=None, code="MALFORMED_MESSAGE", message="x"))
                )

            client.portal.call(plant)

            with pytest.raises(AssertionError, match="does not list"):
                assert_nothing_pending(client, {"alice-1": session})
            session.receive_json()  # drain it, so closing the socket is clean


# --- The two focused message fixtures (Brief §6.2) ---


def _nine_seat_draw_order() -> list[Card]:
    """A deck where seat 4 is dealt `8h 9s`.

    Nine players with the button at seat 1 are dealt clockwise from seat 2, so seat 4 takes the third card of each
    round. Every other seat is hidden from seat 4's view, so the rest of the deck does not matter.
    """
    others = [card for card in Deck.create_new_deck() if card not in (EIGHT_OF_HEARTS, NINE_OF_SPADES)]
    return [others[0], others[1], EIGHT_OF_HEARTS, *others[2:10], NINE_OF_SPADES]


def test_the_nine_seat_snapshot_matches_its_fixture(
    make_app: Any, queue_decks: Any, fixture_json: Any, leak_check: Any, without_messages: Any
) -> None:
    expected = fixture_json("messages/server/snapshot.nine_seats.actor.json")
    table_id = expected["view"]["table_id"]
    queue_decks(_nine_seat_draw_order())
    harness = make_app(
        max_seats=9,
        new_table_id=lambda: table_id,
        new_join_code=lambda: expected["view"]["join_code"],
        choose_button=min,
    )

    with TestClient(harness.app) as client:
        created = client.post("/tables", json={"display_name": NINE_SEAT_NAMES[0]})
        assert created.status_code == 201
        credentials = {NINE_SEAT_NAMES[0]: created.json()["credential"]}
        for seat, name in enumerate(NINE_SEAT_NAMES[1:], start=2):
            joined = client.post(
                f"/tables/by-code/{expected['view']['join_code']}/members",
                json={"display_name": name, "seat": seat},
            )
            assert joined.status_code == 201, joined.json()
            credentials[name] = joined.json()["credential"]

        path = f"/ws/tables/{table_id}"
        with (
            client.websocket_connect(path) as host,
            client.websocket_connect(path) as actor,
        ):
            for session, name in ((host, NINE_SEAT_NAMES[0]), (actor, "Dave")):
                session.send_json({"type": "hello", "protocol": "go-poker.v1", "credential": credentials[name]})
                assert session.receive_json()["revision"] == 9
            host.send_json(
                {"type": "command", "request_id": "a-01", "expected_revision": 9, "name": "start_game", "args": {}}
            )
            snapshot = actor.receive_json()

    assert without_messages(snapshot) == without_messages(expected)
    leak_check(snapshot, harness.identity_texts(*credentials.values()))


def test_the_table_failed_message_matches_its_fixture(
    make_app: Any,
    fixture_json: Any,
    inject_defect: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = fixture_json("messages/server/table_failed.json")
    harness = make_app(new_table_id=lambda: "4f9c2a1e-8d3b-4c5a-9e7f-1a2b3c4d5e6f", new_join_code=lambda: "K7Q2XM")

    with TestClient(harness.app) as client:
        created = client.post("/tables", json={"display_name": "Alice"})
        table_id = created.json()["table_id"]
        runtime = harness.directory.get(table_id)
        assert runtime is not None
        inject_defect(monkeypatch, runtime, "start_game")

        with client.websocket_connect(f"/ws/tables/{table_id}") as session:
            session.send_json({"type": "hello", "protocol": "go-poker.v1", "credential": created.json()["credential"]})
            session.receive_json()
            session.send_json(
                {"type": "command", "request_id": "a-01", "expected_revision": 1, "name": "start_game", "args": {}}
            )

            assert session.receive_json() == expected
            with pytest.raises(WebSocketDisconnect) as closed:
                session.receive_json()
            assert closed.value.code == 4500

    assert harness.directory.get(table_id) is None, "a failed table leaves the directory"


def test_the_replays_check_the_view_and_chip_invariants_on_every_snapshot(
    replay: Any, snapshot_invariants: Any, no_counts: Any
) -> None:
    """The invariants `_replay` runs on each snapshot, counted once over every scenario, so they cannot be vacuous.

    They are the fixtures' own regeneration checks (the fixtures' README, Provenance), re-derived here from the
    server's own messages: hidden-card counts, turn-scoped action fields, pot shapes and chip conservation.
    """
    counts = no_counts
    for path in SCENARIOS:
        for message in replay(_load(path)):
            if message["type"] == "snapshot":
                counts = counts + snapshot_invariants(message)
    # The eight frozen scenarios produce 144 snapshots with a hand, 19 of them settled.
    assert (counts.hands, counts.settled) == (144, 19), counts


def test_every_viewer_of_a_nine_seat_hand_sees_only_its_own_cards(
    make_app: Any,
    queue_decks: Any,
    leak_check: Any,
    snapshot_invariants: Any,
    no_counts: Any,
) -> None:
    """Nine viewers of one hand, each checked on its own (ADR 0005 Consequences, ADR 0009 §10).

    The nine-seat fixture is one actor's view. This drives the same table with every member connected and checks all
    nine redactions at once: each viewer sees two cards of its own and eight hidden hands, the eighteen dealt cards
    are distinct across the viewers, and only the seat whose turn it is carries `legal_actions`.
    """
    queue_decks(_nine_seat_draw_order())
    harness = make_app(max_seats=9, new_join_code=lambda: "K7Q2XM", choose_button=min)

    with TestClient(harness.app) as client:
        created = client.post("/tables", json={"display_name": NINE_SEAT_NAMES[0]})
        assert created.status_code == 201
        table_id = created.json()["table_id"]
        credentials = [created.json()["credential"]]
        for seat, name in enumerate(NINE_SEAT_NAMES[1:], start=2):
            joined = client.post("/tables/by-code/K7Q2XM/members", json={"display_name": name, "seat": seat})
            assert joined.status_code == 201, joined.json()
            credentials.append(joined.json()["credential"])

        path = f"/ws/tables/{table_id}"
        with ExitStack() as connections:
            sessions = [connections.enter_context(client.websocket_connect(path)) for _ in credentials]
            for session, credential in zip(sessions, credentials, strict=True):
                session.send_json({"type": "hello", "protocol": "go-poker.v1", "credential": credential})
                assert session.receive_json()["revision"] == 9
            sessions[0].send_json(
                {"type": "command", "request_id": "a-01", "expected_revision": 9, "name": "start_game", "args": {}}
            )
            snapshots = [session.receive_json() for session in sessions]

    counts = no_counts
    own_cards: list[str] = []
    actors: list[int] = []
    for expected_seat, snapshot in enumerate(snapshots, start=1):
        leak_check(snapshot, harness.identity_texts(*credentials))
        counts = counts + snapshot_invariants(snapshot)
        hand = snapshot["view"]["hand"]
        assert snapshot["view"]["you"]["seat"] == expected_seat
        assert [each["seat"] for each in hand["participants"]] == [1, 2, 3, 4, 5, 6, 7, 8, 9]
        seen = {each["seat"]: each["hole_cards"] for each in hand["participants"]}
        assert seen[expected_seat] is not None and len(seen[expected_seat]) == 2, seen
        assert [seat for seat, cards in seen.items() if cards is not None] == [expected_seat]
        assert [each["hidden_card_count"] for each in hand["participants"] if each["seat"] != expected_seat] == [2] * 8
        own_cards.extend(seen[expected_seat])
        if hand["legal_actions"] is not None:
            actors.append(expected_seat)

    assert len(set(own_cards)) == 18, "the nine viewers were dealt eighteen distinct cards"
    assert len(actors) == 1, f"exactly one viewer may act, not {actors}"
    assert snapshots[actors[0] - 1]["view"]["hand"]["turn"]["seat"] == actors[0]
    assert {snapshot["view"]["hand"]["turn"]["seat"] for snapshot in snapshots} == {actors[0]}
    assert counts.hands == 9
