"""The `HandHistory` foundation: its records are immutable values compared by equality, never by identity."""

import dataclasses

import pytest

from go_poker.game.hand_history import HandHistory, HandParticipant, HandStarted, _appended
from go_poker.game.position import Blind, Position


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
