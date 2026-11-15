"""The snapshot mapping against the canonical snapshots of `heads_up_hand` (ADR 0009 §10, §15).

The hand is replayed over a real `TableSession` and the real engine, from the scenario's `setup` alone: its
`server_defaults`, its `ids`, its `button` rule and its `hands[0].draw_order`. Every snapshot the replay produces is
mapped and kept, so the fixture comparisons and the leak check read the same emission.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from copy import deepcopy
from typing import Any

import pytest

from go_poker.app.identity import UserId
from go_poker.app.results import Accepted, CommandResult
from go_poker.app.session import TableSession
from go_poker.core.card import Card
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.showdown import ShowdownAction
from go_poker.server import dto, mapping

# The hand of `scenarios/heads_up_hand.json`, in the order its steps send the commands.
HAND_ONE_COMMANDS: tuple[tuple[str, Action | ShowdownAction], ...] = (
    ("alice", Action(ActionType.CALL)),
    ("bob", Action(ActionType.CHECK)),
    ("bob", Action(ActionType.BET, 20)),
    ("alice", Action(ActionType.RAISE, 60)),
    ("bob", Action(ActionType.CALL)),
    ("bob", Action(ActionType.CHECK)),
    ("alice", Action(ActionType.CHECK)),
    ("bob", Action(ActionType.CHECK)),
    ("alice", Action(ActionType.BET, 100)),
    ("bob", Action(ActionType.CALL)),
    ("alice", ShowdownAction.SHOW),
    ("bob", ShowdownAction.MUCK),
)

# Every canonical snapshot this replay reaches: the three of the step's scope, plus the showdown decision and the
# settled hand after a muck, which the same replay produces and which cover the showdown and settlement mapping.
CANONICAL_SNAPSHOTS: tuple[tuple[str, str, int, str], ...] = (
    ("snapshot.connected.not_started.json", "alice", 1, "connected"),
    ("snapshot.heads_up.preflop.actor.json", "alice", 3, "command"),
    ("snapshot.heads_up.preflop.waiting.json", "bob", 3, "command"),
    ("snapshot.heads_up.showdown_decision.json", "bob", 14, "command"),
    ("snapshot.heads_up.settled.opponent_mucked.json", "alice", 15, "command"),
)

type Emitted = tuple[str, dto.Snapshot]


def _snapshot_for(session: TableSession, user_id: UserId, cause: dto.SnapshotCause) -> dto.Snapshot:
    """A snapshot of the member's current view: how the server answers a hello or a private command."""
    view = session.view_for(user_id)
    assert view is not None
    return mapping.snapshot(view.revision, cause, view)


def _transition_snapshots(result: Accepted, members: Mapping[UserId, str]) -> list[Emitted]:
    """One snapshot per shared transition per member, mapped from the view captured in that transition."""
    emitted: list[Emitted] = []
    for transition in result.transitions:
        cause = mapping.snapshot_cause(transition.cause)
        for user_id, view in transition.views.items():
            emitted.append((members[user_id], mapping.snapshot(transition.revision, cause, view)))
    return emitted


@pytest.fixture
def heads_up(
    scenario_setup: Callable[[str], Mapping[str, Any]],
    parse_cards: Callable[[Iterable[str]], list[Card]],
    queue_decks: Callable[..., Any],
    make_table: Callable[[Mapping[str, Any], str], tuple[TableSession, Any]],
    join_table: Callable[[TableSession, str, int], Accepted],
    accepted: Callable[[CommandResult], Accepted],
    member_user_id: Callable[[str], UserId],
) -> tuple[Mapping[str, Any], list[Emitted]]:
    """The setup, and every snapshot of hand 1 of `heads_up_hand` in emission order."""
    setup = scenario_setup("heads_up_hand")
    queue_decks(parse_cards(setup["hands"][0]["draw_order"]))
    session, _ = make_table(setup, "alice")
    ids = {name: member_user_id(name) for name in ("alice", "bob")}
    members = {user_id: name for name, user_id in ids.items()}

    emitted: list[Emitted] = [("alice", _snapshot_for(session, ids["alice"], "connected"))]
    emitted += _transition_snapshots(join_table(session, "bob", 2), members)
    emitted.append(("bob", _snapshot_for(session, ids["bob"], "connected")))
    emitted += _transition_snapshots(accepted(session.start_game(ids["alice"], session.revision)), members)
    for actor, action in HAND_ONE_COMMANDS:
        result = accepted(session.act(ids[actor], session.revision, action))
        emitted += _transition_snapshots(result, members)
    return setup, emitted


@pytest.mark.parametrize(("name", "actor", "revision", "cause"), CANONICAL_SNAPSHOTS)
def test_a_mapped_snapshot_equals_its_canonical_fixture(
    heads_up: tuple[Mapping[str, Any], list[Emitted]],
    fixture_json: Callable[[str], Any],
    name: str,
    actor: str,
    revision: int,
    cause: str,
) -> None:
    _, emitted = heads_up
    produced = [
        snapshot
        for viewer, snapshot in emitted
        if viewer == actor and snapshot.revision == revision and snapshot.cause == cause
    ]
    assert len(produced) == 1, f"expected exactly one {cause} snapshot of {actor} at revision {revision}"
    assert produced[0].model_dump(mode="json") == fixture_json(f"messages/server/{name}")


def test_the_replay_produces_a_snapshot_for_every_member_of_every_transition(
    heads_up: tuple[Mapping[str, Any], list[Emitted]],
) -> None:
    _, emitted = heads_up
    for actor in ("alice", "bob"):
        revisions = [snapshot.revision for viewer, snapshot in emitted if viewer == actor]
        assert revisions == sorted(revisions), "revisions never decrease on one connection"
    # Revisions 2 (the join) through 15 (the muck), seen by both members, plus each member's connected snapshot.
    assert sorted(snapshot.revision for viewer, snapshot in emitted if viewer == "bob") == [2, *range(2, 16)]


def test_no_snapshot_of_the_hand_leaks_a_card_or_an_identity(
    heads_up: tuple[Mapping[str, Any], list[Emitted]],
    identity_texts: Callable[[Mapping[str, Any]], list[str]],
    leak_check: Callable[[Mapping[str, Any], Sequence[str]], None],
) -> None:
    setup, emitted = heads_up
    forbidden = identity_texts(setup)
    assert emitted
    for _, snapshot in emitted:
        leak_check(snapshot.model_dump(mode="json"), forbidden)


def test_the_leak_checker_catches_a_planted_leak(
    heads_up: tuple[Mapping[str, Any], list[Emitted]],
    identity_texts: Callable[[Mapping[str, Any]], list[str]],
    leak_check: Callable[[Mapping[str, Any], Sequence[str]], None],
) -> None:
    """The checker that every later step runs on every emitted message must not be vacuous."""
    setup, emitted = heads_up
    forbidden = identity_texts(setup)
    clean = next(s for viewer, s in emitted if viewer == "alice" and s.revision == 3).model_dump(mode="json")

    with_identity = deepcopy(clean)
    with_identity["view"]["seats"][0]["occupant"]["display_name"] = forbidden[0]
    with pytest.raises(AssertionError):
        leak_check(with_identity, forbidden)

    with_card = deepcopy(clean)
    opponent = next(each for each in with_card["view"]["hand"]["participants"] if each["seat"] == 2)
    opponent["hole_cards"] = ["Qs", "Qd"]
    with pytest.raises(AssertionError):
        leak_check(with_card, forbidden)


def test_the_opponents_cards_are_hidden_before_the_showdown_and_after_a_muck(
    heads_up: tuple[Mapping[str, Any], list[Emitted]],
) -> None:
    """The two ends of the hand, read from the mapped snapshots: live hidden cards, then a mucked seat."""
    _, emitted = heads_up
    preflop = next(s for viewer, s in emitted if viewer == "alice" and s.revision == 3)
    opponent = _participant(preflop.view.hand, 2)
    assert (opponent.hole_cards, opponent.hidden_card_count, opponent.has_live_cards) == (None, 2, True)

    settled = next(s for viewer, s in emitted if viewer == "alice" and s.revision == 15)
    mucked = _participant(settled.view.hand, 2)
    assert (mucked.hole_cards, mucked.hidden_card_count, mucked.has_live_cards) == (None, 0, False)


def _participant(hand: dto.Hand | None, seat: int) -> dto.Participant:
    assert hand is not None
    return next(participant for participant in hand.participants if participant.seat == seat)


def test_the_view_mapper_drops_the_revision_and_the_hand_stakes(
    heads_up: tuple[Mapping[str, Any], list[Emitted]],
) -> None:
    """The wire view has no `revision` and no hand `stakes`: the snapshot carries the revision, and `settings` carries
    the blinds. Both exist on the engine's views, so these are the fields the allowlist leaves out."""
    _, emitted = heads_up
    snapshot = next(s for viewer, s in emitted if viewer == "alice" and s.revision == 3)
    serialized = snapshot.model_dump(mode="json")["view"]
    assert "revision" not in serialized
    assert "stakes" not in serialized["hand"]
