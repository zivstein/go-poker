"""A member who is not in the current hand, which no canonical scenario reaches (ADR 0009 §10).

No fixture contains `hole_cards_dealt` with `own_cards: null`, because every scenario's members all play. Two
realistic sequences produce that viewer, and both are checked here:

- a member who sits out before the hand starts and watches it;
- a member who joins over HTTP while a hand is running.

Such a viewer must see a hand with no cards of its own, a card back for every live hand, no legal or showdown
actions, and `own_cards: null` in the log event that dealt the cards.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

JOIN_CODE = "K7Q2XM"
TABLE_ID = "4f9c2a1e-8d3b-4c5a-9e7f-1a2b3c4d5e6f"
BACKS = 2


@dataclass
class Three:
    """Alice (host, seat 1), Bob (seat 2) and Carol (seat 3) at revision 3, nothing started."""

    client: TestClient
    harness: Any
    credentials: dict[str, str]

    @property
    def path(self) -> str:
        return f"/ws/tables/{TABLE_ID}"

    def hello(self, session: WebSocketTestSession, member: str) -> Any:
        session.send_json({"type": "hello", "protocol": "go-poker.v1", "credential": self.credentials[member]})
        return session.receive_json()

    def command(self, session: WebSocketTestSession, request_id: str, revision: int, **rest: Any) -> None:
        session.send_json({"type": "command", "request_id": request_id, "expected_revision": revision, **rest})


@pytest.fixture
def three(
    make_app: Callable[..., Any],
    queue_decks: Callable[..., Any],
    parse_cards: Callable[..., Any],
    fixture_json: Callable[[str], Any],
) -> Iterator[Three]:
    setup = fixture_json("scenarios/three_way_side_pots.json")["setup"]
    queue_decks(*(parse_cards(hand["draw_order"]) for hand in setup["hands"]))
    harness = make_app(new_table_id=lambda: TABLE_ID, new_join_code=lambda: JOIN_CODE, choose_button=min)
    with TestClient(harness.app) as client:
        created = client.post("/tables", json={"display_name": "Alice"}).json()
        credentials = {"alice": created["credential"]}
        for name, seat in (("Bob", 2), ("Carol", 3)):
            joined = client.post(f"/tables/by-code/{JOIN_CODE}/members", json={"display_name": name, "seat": seat})
            assert joined.status_code == 201, joined.json()
            credentials[name.lower()] = joined.json()["credential"]
        harness.credentials.extend(credentials.values())
        yield Three(client=client, harness=harness, credentials=credentials)


def _assert_sees_no_cards(snapshot: Any, viewer: int, participants: list[int]) -> None:
    """The whole redaction of a viewer with no hand: no cards, a back for every live hand, nothing to act on."""
    view = snapshot["view"]
    hand = view["hand"]
    assert view["you"]["seat"] == viewer
    assert hand is not None, "a watching member still sees the hand"
    assert [each["seat"] for each in hand["participants"]] == participants
    assert viewer not in participants, "this viewer is deliberately not in the hand"
    for participant in hand["participants"]:
        assert participant["hole_cards"] is None, participant
        assert participant["strength"] is None, participant
        assert participant["hidden_card_count"] == (BACKS if participant["has_live_cards"] else 0), participant
    assert hand["legal_actions"] is None
    assert hand["showdown_actions"] is None
    dealt = [event for event in hand["log"] if event["event"] == "hole_cards_dealt"]
    assert dealt, "the log records the deal"
    assert [event["own_cards"] for event in dealt] == [None] * len(dealt), dealt
    assert view["you"]["pre_action_options"] == [], "a member with no hand has nothing to pre-select"


def test_a_member_sitting_out_watches_the_hand_and_sees_no_card(
    three: Three,
    leak_check: Callable[..., None],
    snapshot_invariants: Callable[..., Any],
    drain_socket: Callable[..., list[Any]],
) -> None:
    with (
        three.client.websocket_connect(three.path) as alice,
        three.client.websocket_connect(three.path) as carol,
    ):
        three.hello(alice, "alice")
        three.hello(carol, "carol")

        three.command(carol, "c-01", 3, name="sit_out", args={})
        assert [message["type"] for message in drain_socket(three.client, carol)] == ["snapshot", "accepted"]
        drain_socket(three.client, alice)

        three.command(alice, "a-01", 4, name="start_game", args={})

        snapshots = [message for message in drain_socket(three.client, carol) if message["type"] == "snapshot"]
        assert len(snapshots) == 1, snapshots
        snapshot = snapshots[0]
        _assert_sees_no_cards(snapshot, viewer=3, participants=[1, 2])
        leak_check(snapshot, three.harness.identity_texts())
        assert snapshot_invariants(snapshot).hands == 1
        seats = {seat["seat"]: seat["occupant"] for seat in snapshot["view"]["seats"]}
        assert seats[3] is not None and seats[3]["status"] == "sitting_out"


def test_a_member_who_joins_during_a_hand_sees_it_without_any_card(
    three: Three,
    make_app: Callable[..., Any],
    leak_check: Callable[..., None],
    snapshot_invariants: Callable[..., Any],
    drain_socket: Callable[..., list[Any]],
) -> None:
    """A fourth member joins over HTTP while the hand runs: her `connected` snapshot is the hand she is not in."""
    with (
        three.client.websocket_connect(three.path) as alice,
        three.client.websocket_connect(three.path) as bob,
    ):
        three.hello(alice, "alice")
        three.hello(bob, "bob")
        three.command(alice, "a-01", 3, name="start_game", args={})
        drain_socket(three.client, alice)
        drain_socket(three.client, bob)

        joined = three.client.post(f"/tables/by-code/{JOIN_CODE}/members", json={"display_name": "Dave", "seat": 4})
        assert joined.status_code == 201, joined.json()
        three.harness.credentials.append(joined.json()["credential"])

        with three.client.websocket_connect(three.path) as dave:
            dave.send_json({"type": "hello", "protocol": "go-poker.v1", "credential": joined.json()["credential"]})
            snapshot = dave.receive_json()

            assert snapshot["cause"] == "connected"
            _assert_sees_no_cards(snapshot, viewer=4, participants=[1, 2, 3])
            leak_check(snapshot, three.harness.identity_texts())
            assert snapshot_invariants(snapshot).hands == 1
            seats = {seat["seat"]: seat["occupant"] for seat in snapshot["view"]["seats"]}
            assert seats[4] is not None and seats[4]["status"] == "waiting_to_join"
            assert drain_socket(three.client, dave) == [], "the welcome snapshot is the only one"
