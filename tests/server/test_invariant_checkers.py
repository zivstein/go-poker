"""The invariant checkers must be able to fail, or the replays prove nothing.

`conftest`'s `snapshot_invariants` and `snapshot_follows` run on every snapshot of every replay. Each rule they claim
to check is planted here as a violation of a canonical snapshot, and each must be caught. The two canonical snapshots
used are an in-hand one (with `legal_actions`) and a settled one (with `pot_awards`).
"""

from collections.abc import Callable
from copy import deepcopy
from typing import Any

import pytest

ACTOR = "messages/server/snapshot.heads_up.preflop.actor.json"
WAITING = "messages/server/snapshot.heads_up.preflop.waiting.json"
SETTLED = "messages/server/snapshot.heads_up.settled.opponent_mucked.json"
SIDE_POTS = "messages/server/snapshot.side_pots.settled.json"


@pytest.fixture
def actor(fixture_json: Callable[[str], Any]) -> Any:
    return deepcopy(fixture_json(ACTOR))


@pytest.fixture
def settled(fixture_json: Callable[[str], Any]) -> Any:
    return deepcopy(fixture_json(SETTLED))


def test_the_canonical_snapshots_satisfy_the_invariants(
    fixture_json: Callable[[str], Any], snapshot_invariants: Callable[..., Any]
) -> None:
    """The baseline: the checker passes on the contract's own snapshots, including the known side-pot layering."""
    assert snapshot_invariants(fixture_json(ACTOR)) == snapshot_invariants(fixture_json(WAITING))
    assert snapshot_invariants(fixture_json(ACTOR)).hands == 1
    assert snapshot_invariants(fixture_json(SETTLED)).settled == 1
    assert snapshot_invariants(fixture_json(SIDE_POTS)).settled == 1


def _participant(snapshot: Any, seat: int) -> Any:
    return next(each for each in snapshot["view"]["hand"]["participants"] if each["seat"] == seat)


def _seat(snapshot: Any, seat: int) -> Any:
    return next(each for each in snapshot["view"]["seats"] if each["seat"] == seat)


def test_a_wrong_hidden_card_count_is_caught(actor: Any, snapshot_invariants: Callable[..., Any]) -> None:
    hidden = next(each for each in actor["view"]["hand"]["participants"] if each["hole_cards"] is None)
    hidden["hidden_card_count"] = 0
    with pytest.raises(AssertionError):
        snapshot_invariants(actor)


def test_a_card_back_counted_for_the_viewers_own_hand_is_caught(
    actor: Any, snapshot_invariants: Callable[..., Any]
) -> None:
    own = _participant(actor, actor["view"]["you"]["seat"])
    assert own["hole_cards"] is not None
    own["hidden_card_count"] = 2
    with pytest.raises(AssertionError):
        snapshot_invariants(actor)


def test_legal_actions_in_the_view_of_a_seat_that_may_not_act_are_caught(
    fixture_json: Callable[[str], Any], snapshot_invariants: Callable[..., Any]
) -> None:
    waiting = deepcopy(fixture_json(WAITING))
    actor = fixture_json(ACTOR)
    assert waiting["view"]["hand"]["legal_actions"] is None
    waiting["view"]["hand"]["legal_actions"] = actor["view"]["hand"]["legal_actions"]
    with pytest.raises(AssertionError):
        snapshot_invariants(waiting)


def test_showdown_actions_in_the_wrong_view_are_caught(actor: Any, snapshot_invariants: Callable[..., Any]) -> None:
    actor["view"]["hand"]["showdown_actions"] = ["show", "muck"]
    with pytest.raises(AssertionError):
        snapshot_invariants(actor)


def test_a_strength_without_the_cards_it_belongs_to_is_caught(
    settled: Any, snapshot_invariants: Callable[..., Any]
) -> None:
    hidden = next(each for each in settled["view"]["hand"]["participants"] if each["hole_cards"] is None)
    shown = next(each for each in settled["view"]["hand"]["participants"] if each["strength"] is not None)
    hidden["strength"] = shown["strength"]
    with pytest.raises(AssertionError):
        snapshot_invariants(settled)


def test_a_pot_whose_eligible_seats_are_not_ascending_is_caught(
    actor: Any, snapshot_invariants: Callable[..., Any]
) -> None:
    actor["view"]["hand"]["pots"] = [{"amount": 30, "eligible_seats": [2, 1]}]
    with pytest.raises(AssertionError):
        snapshot_invariants(actor)


def test_chips_invented_in_a_pot_are_caught(actor: Any, snapshot_invariants: Callable[..., Any]) -> None:
    hand = actor["view"]["hand"]
    hand["pots"] = [{"amount": sum(pot["amount"] for pot in hand["pots"]) + 5, "eligible_seats": [1, 2]}]
    with pytest.raises(AssertionError):
        snapshot_invariants(actor)


def test_a_stack_that_does_not_match_the_hands_chips_is_caught(
    actor: Any, snapshot_invariants: Callable[..., Any]
) -> None:
    _seat(actor, 1)["occupant"]["stack"] += 1
    with pytest.raises(AssertionError):
        snapshot_invariants(actor)


def test_an_award_whose_shares_do_not_add_up_is_caught(settled: Any, snapshot_invariants: Callable[..., Any]) -> None:
    award = settled["view"]["hand"]["settlement"]["pot_awards"][0]
    award["shares"][0]["amount"] += 1
    with pytest.raises(AssertionError):
        snapshot_invariants(settled)


def test_an_award_to_a_seat_that_was_not_eligible_is_caught(
    settled: Any, snapshot_invariants: Callable[..., Any]
) -> None:
    award = settled["view"]["hand"]["settlement"]["pot_awards"][0]
    award["eligible_seats"] = [seat for seat in award["eligible_seats"] if seat != award["shares"][0]["seat"]]
    with pytest.raises(AssertionError):
        snapshot_invariants(settled)


def test_awards_that_do_not_equal_the_pots_are_caught(settled: Any, snapshot_invariants: Callable[..., Any]) -> None:
    settled["view"]["hand"]["pots"][0]["amount"] += 10
    with pytest.raises(AssertionError):
        snapshot_invariants(settled)


def test_a_settled_stack_that_was_not_paid_is_caught(settled: Any, snapshot_invariants: Callable[..., Any]) -> None:
    _seat(settled, 1)["occupant"]["stack"] -= 10
    with pytest.raises(AssertionError):
        snapshot_invariants(settled)


def test_a_missing_seat_is_caught(actor: Any, snapshot_invariants: Callable[..., Any]) -> None:
    actor["view"]["seats"] = actor["view"]["seats"][:-1]
    with pytest.raises(AssertionError):
        snapshot_invariants(actor)


# --- The per-connection order (ADR 0009 §9.1, §9.3) ---


def test_a_revision_going_backwards_on_one_connection_is_caught(
    fixture_json: Callable[[str], Any], snapshot_follows: Callable[..., None]
) -> None:
    newer = fixture_json(SETTLED)
    older = fixture_json(ACTOR)
    assert newer["revision"] > older["revision"]
    snapshot_follows(older, newer)
    with pytest.raises(AssertionError, match="backwards"):
        snapshot_follows(newer, older)


def test_two_snapshots_at_one_revision_may_differ_only_in_the_private_you_fields(
    actor: Any, fixture_json: Callable[[str], Any], snapshot_follows: Callable[..., None]
) -> None:
    same = deepcopy(fixture_json(ACTOR))
    same["cause"] = "private"
    same["view"]["you"]["pending_sit_out"] = not same["view"]["you"]["pending_sit_out"]
    same["view"]["you"]["pre_action"] = {"kind": "check", "amount": None}
    snapshot_follows(actor, same)

    shared_change = deepcopy(fixture_json(ACTOR))
    _seat(shared_change, 1)["occupant"]["stack"] += 1
    with pytest.raises(AssertionError, match="private"):
        snapshot_follows(actor, shared_change)
