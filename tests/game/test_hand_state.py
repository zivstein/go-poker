import pytest

from go_poker.core.card import Card, Rank, Suit
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.position import Blind, Position


@pytest.mark.parametrize(
    "position, blind",
    [
        pytest.param(Position.BTN, Blind.NONE, id="button"),
        pytest.param(Position.SB, Blind.SMALL, id="small-blind"),
        pytest.param(Position.BB, Blind.BIG, id="big-blind"),
        pytest.param(Position.BTN, Blind.SMALL, id="heads-up-button"),
    ],
)
def test_hand_player_state_keeps_player_and_assignment(position: Position, blind: Blind) -> None:
    """Store the supplied player reference and assignment without changing the player."""
    player = Player("Ziv", stack=1000, status=PlayerStatus.READY)
    state = HandPlayerState(player=player, seat_number=3, position=position, blind=blind)
    assert state.player is player
    assert state.seat_number == 3
    assert state.position == position
    assert state.blind == blind
    assert state.folded is False
    assert state.all_in is False
    assert (state.street_contribution, state.total_contribution) == (0, 0)
    assert state.hole_cards == []
    assert player.stack == 1000
    assert player.status == PlayerStatus.READY


@pytest.mark.parametrize("folded, all_in", [(True, False), (False, True)], ids=["folded", "all-in"])
def test_hand_player_state_accepts_explicit_flags(folded: bool, all_in: bool) -> None:
    """Explicit flags override the default values when constructing hand state."""
    player = Player("Ziv", stack=1000)
    state = HandPlayerState(player, 1, Position.BTN, Blind.NONE, folded=folded, all_in=all_in)
    assert state.folded is folded
    assert state.all_in is all_in


@pytest.mark.parametrize("flag", ["folded", "all_in"])
def test_hand_flags_are_independent_between_hands(flag: str) -> None:
    """A flag change belongs to one hand state, even when the player is shared."""
    player = Player("Ziv", stack=1000, status=PlayerStatus.READY)
    first_hand = HandPlayerState(player, 1, Position.BTN, Blind.NONE)
    second_hand = HandPlayerState(player, 1, Position.BB, Blind.BIG)
    setattr(first_hand, flag, True)
    assert first_hand.folded is (flag == "folded")
    assert first_hand.all_in is (flag == "all_in")
    assert second_hand.folded is False
    assert second_hand.all_in is False
    assert player.status == PlayerStatus.READY
    assert player.stack == 1000


def test_hand_player_state_reflects_player_stack_changes() -> None:
    """Hand state references the live player rather than a copy of their stack."""
    player = Player("Ziv", stack=1000)
    state = HandPlayerState(player, 1, Position.BTN, Blind.NONE)
    player.stack = 800
    assert state.player.stack == 800


def test_hole_cards_are_not_shared_between_hand_states() -> None:
    """Each hand state starts with its own empty hole-card list, even for the same player."""
    player = Player("Ziv", stack=1000)
    first_hand = HandPlayerState(player, 1, Position.BTN, Blind.NONE)
    second_hand = HandPlayerState(player, 1, Position.BB, Blind.BIG)
    assert first_hand.hole_cards is not second_hand.hole_cards
    first_hand.hole_cards.append(Card(Rank.ACE, Suit.SPADES))
    assert second_hand.hole_cards == []
