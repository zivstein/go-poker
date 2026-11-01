import copy
from typing import Any

import pytest

from go_poker.core.deck import Deck
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_history import BlindPost, BlindsPosted, HandHistory, HandParticipant, HandStarted
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import InvalidHandNumberError, PokerHand
from go_poker.game.position import Blind, Position
from go_poker.game.street import Street


def make_players() -> tuple[HandPlayerState, ...]:
    assignments = [
        (5, Position.BTN, Blind.NONE),
        (8, Position.SB, Blind.SMALL),
        (2, Position.BB, Blind.BIG),
    ]
    return tuple(
        HandPlayerState(
            player=Player(f"P{seat_number}", stack=1000, status=PlayerStatus.READY),
            seat_number=seat_number,
            position=position,
            blind=blind,
        )
        for seat_number, position, blind in assignments
    )


def test_new_hand_holds_the_given_players_and_deck() -> None:
    """The hand holds the given participant states, in the given order, and the given deck itself."""
    players = make_players()
    deck = Deck()
    hand = PokerHand(players=players, deck=deck, number=1)
    assert all(held is given for held, given in zip(hand.players, players, strict=True))
    assert hand.deck is deck


def test_new_hand_starts_preflop_with_empty_board_nothing_burned_no_betting_and_unsettled() -> None:
    """A new hand starts on the preflop street with no community cards, no burned cards, no betting state and no
    settlement."""
    hand = PokerHand(players=make_players(), deck=Deck(), number=1)
    assert hand.street is Street.PREFLOP
    assert hand.board == []
    assert hand.burned_cards == []
    assert hand.betting is None
    assert hand.settlement is None


def test_hands_do_not_share_board_or_burned_cards() -> None:
    """Each hand gets its own board and burned cards, so dealing in one hand never affects another."""
    first = PokerHand(players=make_players(), deck=Deck(), number=1)
    second = PokerHand(players=make_players(), deck=Deck(), number=1)
    assert first.board is not second.board
    assert first.burned_cards is not second.burned_cards

    first.burned_cards.append(first.deck.draw())
    first.board.append(first.deck.draw())
    assert second.board == []
    assert second.burned_cards == []


# =============================================================================
# NUMBER AND HISTORY
# =============================================================================


def literal_started(number: int = 1) -> HandStarted:
    """The `HandStarted` that `make_players()` should produce, written out independently of the implementation."""
    return HandStarted(
        number=number,
        participants=(
            HandParticipant(5, "P5", Position.BTN, Blind.NONE, 1000),
            HandParticipant(8, "P8", Position.SB, Blind.SMALL, 1000),
            HandParticipant(2, "P2", Position.BB, Blind.BIG, 1000),
        ),
    )


def test_new_hand_records_exactly_one_hand_started_event_in_hand_order() -> None:
    """Construction records `HandStarted` as the only event, with the participants in the given (hand) order."""
    hand = PokerHand(players=make_players(), deck=Deck(), number=3)
    assert hand.history.events == (literal_started(3),)
    assert hand.history == HandHistory((literal_started(3),))


def test_number_is_read_from_the_history() -> None:
    """The hand number, the history's number and the first event's number are the same value."""
    hand = PokerHand(players=make_players(), deck=Deck(), number=12)
    assert hand.number == hand.history.number == hand.history.events[0].number == 12


def test_number_is_read_only() -> None:
    """The number is a property of the history, not a settable field."""
    hand = PokerHand(players=make_players(), deck=Deck(), number=1)
    with pytest.raises(AttributeError):
        hand.number = 2  # type: ignore[misc]


def test_constructor_requires_number_and_takes_no_state_fields() -> None:
    """The constructor requires `number` and takes no state fields (board, history)."""
    with pytest.raises(TypeError):
        PokerHand(players=make_players(), deck=Deck(), number=1, board=[])  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        PokerHand(players=make_players(), deck=Deck(), number=1, history=HandHistory(()))  # type: ignore[call-arg]
    with pytest.raises(TypeError):
        PokerHand(players=make_players(), deck=Deck())  # type: ignore[call-arg]


@pytest.mark.parametrize("number", [0, -1, -100, True, False, 1.0, 2.5, "1", None], ids=repr)
def test_new_hand_rejects_a_number_that_is_not_a_positive_integer(number: Any) -> None:
    """Zero, negatives, booleans and non-integers are rejected."""
    with pytest.raises(InvalidHandNumberError):
        PokerHand(players=make_players(), deck=Deck(), number=number)


@pytest.mark.parametrize("number", [1, 2, 7, 10**6])
def test_new_hand_accepts_any_positive_integer(number: int) -> None:
    assert PokerHand(players=make_players(), deck=Deck(), number=number).number == number


def test_the_number_is_validated_before_the_players_are_read() -> None:
    """A bad number is rejected without looking at the participants."""
    with pytest.raises(InvalidHandNumberError):
        PokerHand(players=(), deck=Deck(), number=0)


def test_starting_stacks_are_the_stacks_before_any_blind_and_do_not_follow_the_players() -> None:
    """The history holds values: later changes to the live players never change a history taken earlier."""
    players = make_players()
    hand = PokerHand(players=players, deck=Deck(), number=1)
    history = hand.history
    expected = HandHistory((literal_started(),))
    assert history == expected

    for state in players:
        state.player.stack -= 123
        state.player.status = PlayerStatus.SITTING_OUT
        state.folded = True
        state.total_contribution = 123

    assert history == expected
    assert hand.history == expected


def test_beginning_betting_leaves_the_starting_stacks_in_the_history_unchanged() -> None:
    """The blinds are taken from the stacks afterwards; the history still records the stacks before them in
    `HandStarted`, which only the blinds event follows."""
    hand = PokerHand(players=make_players(), deck=Deck(), number=1)
    stakes = Stakes(small_blind=5, big_blind=10)
    initialize_betting(hand, stakes)
    assert [state.player.stack for state in hand.players] == [1000, 995, 990]
    assert hand.history == HandHistory(
        (
            literal_started(),
            BlindsPosted(stakes, (BlindPost(8, Blind.SMALL, 5, False), BlindPost(2, Blind.BIG, 10, False))),
        )
    )


def test_hands_do_not_share_a_history() -> None:
    first = PokerHand(players=make_players(), deck=Deck(), number=1)
    second = PokerHand(players=make_players(), deck=Deck(), number=2)
    assert first.history != second.history
    assert first.history.events == (literal_started(1),)


def test_hand_repr_and_equality_include_the_history() -> None:
    """The history is a dataclass field, so it takes part in repr and equality."""
    players = make_players()
    deck = Deck()
    assert PokerHand(players, deck, 1) == PokerHand(players, deck, 1)
    assert PokerHand(players, deck, 1) != PokerHand(players, deck, 2)
    assert "history=HandHistory(" in repr(PokerHand(players, deck, 1))


def test_a_deep_copied_hand_keeps_its_number_and_history_and_shares_nothing() -> None:
    """Copying a hand (it has a custom constructor) neither re-validates nor re-records, and the copy is independent."""
    hand = PokerHand(players=make_players(), deck=Deck(), number=4)
    copied = copy.deepcopy(hand)
    assert copied is not hand and copied.number == 4
    assert copied.history == hand.history == HandHistory((literal_started(4),))
    assert len(copied.history.events) == 1

    copied.players[0].player.stack = 1
    assert hand.players[0].player.stack == 1000
    assert copied.history == HandHistory((literal_started(4),))
