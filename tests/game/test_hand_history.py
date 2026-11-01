"""The `HandHistory` foundation: its records are immutable values compared by equality, never by identity."""

import dataclasses

import pytest

from go_poker.core.card import Card, Rank, Suit
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_history import (
    ActionTaken,
    BettingRoundCompleted,
    BettingRoundStarted,
    BlindPost,
    BlindsPosted,
    ChipsReturned,
    HandHistory,
    HandParticipant,
    HandStarted,
    HoleCardsDealt,
    SeatHoleCards,
    StreetDealt,
    _appended,
)
from go_poker.game.position import Blind, Position
from go_poker.game.street import Street


def participant(seat: int, player_id: str, position: Position, blind: Blind, stack: int = 1000) -> HandParticipant:
    return HandParticipant(seat=seat, player_id=player_id, position=position, blind=blind, starting_stack=stack)


def started(number: int = 1) -> HandStarted:
    return HandStarted(
        number=number,
        participants=(
            participant(4, "P4", Position.BTN, Blind.NONE),
            participant(6, "P6", Position.SB, Blind.SMALL, 500),
            participant(2, "P2", Position.BB, Blind.BIG, 250),
        ),
    )


def test_participant_holds_its_facts() -> None:
    """A participant records the seat, the id, the position, the blind and the pre-blind stack."""
    seat = participant(6, "P6", Position.SB, Blind.SMALL, 500)
    assert (seat.seat, seat.player_id, seat.position, seat.blind, seat.starting_stack) == (
        6,
        "P6",
        Position.SB,
        Blind.SMALL,
        500,
    )


def test_history_reads_number_and_participants_from_its_first_event() -> None:
    """The history holds only its events; the number and participants are read from `HandStarted`."""
    event = started(number=7)
    history = HandHistory((event,))
    assert [field.name for field in dataclasses.fields(history)] == ["events"]
    assert history.events == (event,)
    assert history.number == 7
    assert history.participants == event.participants


def test_equal_ids_that_are_not_the_same_object_give_equal_records() -> None:
    """Records are compared by value: equal id strings that are distinct objects make equal participants."""
    first_id = "".join(["P", "1"])
    second_id = "".join(["P", "1"])
    assert first_id is not second_id
    first = participant(1, first_id, Position.BTN, Blind.NONE)
    second = participant(1, second_id, Position.BTN, Blind.NONE)
    assert first == second
    assert HandHistory((HandStarted(1, (first,)),)) == HandHistory((HandStarted(1, (second,)),))
    assert hash(first) == hash(second)


def test_different_facts_give_unequal_records() -> None:
    """Every fact takes part in equality."""
    base = participant(1, "P1", Position.BTN, Blind.NONE)
    others = [
        participant(2, "P1", Position.BTN, Blind.NONE),
        participant(1, "P2", Position.BTN, Blind.NONE),
        participant(1, "P1", Position.BB, Blind.NONE),
        participant(1, "P1", Position.BTN, Blind.SMALL),
        participant(1, "P1", Position.BTN, Blind.NONE, 999),
    ]
    assert all(base != other for other in others)
    assert started(1) != started(2)


def test_records_are_frozen() -> None:
    """Participants, events and histories cannot be changed in place."""
    seat = participant(1, "P1", Position.BTN, Blind.NONE)
    event = HandStarted(1, (seat,))
    history = HandHistory((event,))
    with pytest.raises(dataclasses.FrozenInstanceError):
        seat.starting_stack = 1  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.number = 2  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        history.events = ()  # type: ignore[misc]
    assert isinstance(history.events, tuple)
    assert isinstance(event.participants, tuple)


def test_appended_returns_a_new_history_one_event_longer_and_leaves_the_original_alone() -> None:
    """Recording replaces the history with a new value; a history taken earlier never changes."""
    original = HandHistory((started(),))
    copy_of_original = HandHistory((started(),))

    longer = _appended(original, started(2))

    assert longer is not original
    assert longer.events == (*original.events, started(2))
    assert len(longer.events) == len(original.events) + 1
    assert original == copy_of_original
    assert original.events == (started(),)
    assert longer.number == 1  # still read from the first event


# =============================================================================
# TRANSITION EVENTS
# =============================================================================

ACE = Card(Rank.ACE, Suit.SPADES)
KING = Card(Rank.KING, Suit.HEARTS)
TWO = Card(Rank.TWO, Suit.CLUBS)
THREE = Card(Rank.THREE, Suit.CLUBS)
STAKES = Stakes(5, 10)


def all_events() -> list[object]:
    """One of every transition event, each built fresh so that equal events are distinct objects."""
    return [
        BlindPost(2, Blind.SMALL, 5, False),
        BlindsPosted(STAKES, (BlindPost(2, Blind.SMALL, 5, False), BlindPost(3, Blind.BIG, 10, False))),
        SeatHoleCards(2, (ACE, KING)),
        HoleCardsDealt((SeatHoleCards(2, (ACE, KING)), SeatHoleCards(3, (TWO, THREE)))),
        StreetDealt(Street.FLOP, (TWO,), (ACE, KING, THREE)),
        BettingRoundStarted(Street.FLOP),
        ActionTaken(2, Action(ActionType.RAISE, 30), 25, False),
        ChipsReturned(2, 10),
        BettingRoundCompleted(Street.FLOP),
    ]


def test_every_transition_event_is_frozen() -> None:
    """No event, nor a post or a seat's cards, can be changed in place."""
    for event in all_events():
        field_name = dataclasses.fields(event)[0].name  # type: ignore[arg-type]
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(event, field_name, None)


def test_equal_transition_events_are_equal_by_value_and_hash_alike() -> None:
    """Two independently built events with the same facts are equal, whatever object they are."""
    for first, second in zip(all_events(), all_events(), strict=True):
        assert first is not second
        assert first == second
        assert hash(first) == hash(second)


def test_every_fact_of_a_transition_event_takes_part_in_equality() -> None:
    """Changing any one fact makes the event unequal."""
    post = BlindPost(2, Blind.SMALL, 5, False)
    assert post != BlindPost(3, Blind.SMALL, 5, False)
    assert post != BlindPost(2, Blind.BIG, 5, False)
    assert post != BlindPost(2, Blind.SMALL, 4, False)
    assert post != BlindPost(2, Blind.SMALL, 5, True)
    assert BlindsPosted(STAKES, (post,)) != BlindsPosted(Stakes(5, 20), (post,))
    assert BlindsPosted(STAKES, (post,)) != BlindsPosted(STAKES, ())
    assert SeatHoleCards(2, (ACE, KING)) != SeatHoleCards(2, (KING, ACE))  # the order received matters
    assert StreetDealt(Street.FLOP, (TWO,), (ACE,)) != StreetDealt(Street.TURN, (TWO,), (ACE,))
    assert StreetDealt(Street.FLOP, (TWO,), (ACE,)) != StreetDealt(Street.FLOP, (THREE,), (ACE,))
    assert StreetDealt(Street.FLOP, (TWO,), (ACE,)) != StreetDealt(Street.FLOP, (TWO,), (KING,))
    assert BettingRoundStarted(Street.FLOP) != BettingRoundStarted(Street.TURN)
    taken = ActionTaken(2, Action(ActionType.RAISE, 30), 25, False)
    assert taken != ActionTaken(3, Action(ActionType.RAISE, 30), 25, False)
    assert taken != ActionTaken(2, Action(ActionType.RAISE, 40), 25, False)
    assert taken != ActionTaken(2, Action(ActionType.BET, 30), 25, False)
    assert taken != ActionTaken(2, Action(ActionType.RAISE, 30), 20, False)
    assert taken != ActionTaken(2, Action(ActionType.RAISE, 30), 25, True)
    assert ChipsReturned(2, 10) != ChipsReturned(3, 10)
    assert ChipsReturned(2, 10) != ChipsReturned(2, 11)
    assert BettingRoundCompleted(Street.FLOP) != BettingRoundCompleted(Street.RIVER)
    assert BettingRoundStarted(Street.FLOP) != BettingRoundCompleted(Street.FLOP)


def test_events_hold_only_immutable_values() -> None:
    """Sequences are tuples, never lists, so an event cannot be changed through a field."""
    blinds = BlindsPosted(STAKES, (BlindPost(2, Blind.SMALL, 5, False),))
    dealt = HoleCardsDealt((SeatHoleCards(2, (ACE, KING)),))
    street = StreetDealt(Street.FLOP, (TWO,), (ACE, KING, THREE))
    assert isinstance(blinds.posts, tuple)
    assert isinstance(dealt.hole_cards, tuple) and isinstance(dealt.hole_cards[0].cards, tuple)
    assert isinstance(street.burned, tuple) and isinstance(street.cards, tuple)


def test_history_reads_number_and_participants_across_many_events() -> None:
    """The number and participants are read from the first event, however many events follow."""
    first = started(9)
    history = HandHistory((first, *all_events()))  # type: ignore[arg-type]
    assert history.number == 9
    assert history.participants == first.participants
    assert len(history.events) == 1 + len(all_events())


def test_a_history_that_does_not_start_with_hand_started_raises_type_error_when_read() -> None:
    """A malformed first event is not silently read; construction itself does not validate."""
    history = HandHistory((BettingRoundStarted(Street.FLOP), started()))
    with pytest.raises(TypeError, match="starts with HandStarted"):
        _ = history.number
    with pytest.raises(TypeError, match="starts with HandStarted"):
        _ = history.participants
