from go_poker.core.deck import Deck
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
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
    hand = PokerHand(players=players, deck=deck)
    assert all(held is given for held, given in zip(hand.players, players, strict=True))
    assert hand.deck is deck


def test_new_hand_starts_preflop_with_empty_board_nothing_burned_no_betting_and_unsettled() -> None:
    """A new hand starts on the preflop street with no community cards, no burned cards, no betting state and no
    settlement."""
    hand = PokerHand(players=make_players(), deck=Deck())
    assert hand.street is Street.PREFLOP
    assert hand.board == []
    assert hand.burned_cards == []
    assert hand.betting is None
    assert hand.settlement is None


def test_hands_do_not_share_board_or_burned_cards() -> None:
    """Each hand gets its own board and burned cards, so dealing in one hand never affects another."""
    first = PokerHand(players=make_players(), deck=Deck())
    second = PokerHand(players=make_players(), deck=Deck())
    assert first.board is not second.board
    assert first.burned_cards is not second.burned_cards

    first.burned_cards.append(first.deck.draw())
    first.board.append(first.deck.draw())
    assert second.board == []
    assert second.burned_cards == []
