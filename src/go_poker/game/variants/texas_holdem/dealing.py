from go_poker.core.deck import DeckEmptyError
from go_poker.game.poker_hand import PokerHand
from go_poker.game.street import Street

HOLE_CARD_COUNT = 2
BURN_CARD_COUNT = 1
# Board cards dealt when the hand enters each street.
BOARD_CARD_COUNTS = {Street.FLOP: 3, Street.TURN: 1, Street.RIVER: 1}

_NEXT_STREET = {Street.PREFLOP: Street.FLOP, Street.FLOP: Street.TURN, Street.TURN: Street.RIVER}


class HoleCardsAlreadyDealtError(RuntimeError):
    """Raised when dealing hole cards to a hand in which a participant already holds hole cards."""


class HandPastPreflopError(RuntimeError):
    """Raised when dealing hole cards to a hand that is no longer on the preflop street."""


class InvalidHoleCardCountError(RuntimeError):
    """Raised when board cards are dealt or a showdown is evaluated while a player lacks exactly two hole cards."""


class NoNextStreetError(RuntimeError):
    """Raised when moving a hand past the river."""


def deal_hole_cards(hand: PokerHand) -> None:
    """Deal HOLE_CARD_COUNT cards to every participant from the hand's deck, one card per player per round.

    Each round starts with the player clockwise of the button and ends with the button. No card is burned.
    The hand is validated before any card is drawn, so a failure leaves it unchanged.
    """
    if hand.street is not Street.PREFLOP:
        raise HandPastPreflopError(f"Hole cards are dealt preflop, but the hand is on the {hand.street.value}")

    if any(state.hole_cards for state in hand.players):
        raise HoleCardsAlreadyDealtError("Hole cards have already been dealt in this hand")

    cards_needed = HOLE_CARD_COUNT * len(hand.players)
    if len(hand.deck) < cards_needed:
        raise DeckEmptyError(f"The deck has {len(hand.deck)} cards but dealing hole cards needs {cards_needed}")

    # Players are ordered clockwise from the button, so the deal starts at the next player and ends at the button.
    deal_order = hand.players[1:] + hand.players[:1]
    for _ in range(HOLE_CARD_COUNT):
        for state in deal_order:
            state.hole_cards.append(hand.deck.draw())


def deal_next_street(hand: PokerHand) -> None:
    """Move the hand to its next street: burn BURN_CARD_COUNT cards, then deal that street's board cards.

    Streets go preflop, flop, turn, river. Every participant must hold exactly HOLE_CARD_COUNT hole cards first.
    Burned cards go to the hand's burned cards and board cards onto its board, in draw order. The hand is validated
    before any card is drawn, so a failure leaves it unchanged.
    """
    next_street = _NEXT_STREET.get(hand.street)
    if next_street is None:
        raise NoNextStreetError(f"There is no street after the {hand.street.value}")

    if any(len(state.hole_cards) != HOLE_CARD_COUNT for state in hand.players):
        raise InvalidHoleCardCountError(
            f"Board cards are dealt only once every participant holds exactly {HOLE_CARD_COUNT} hole cards"
        )

    board_card_count = BOARD_CARD_COUNTS[next_street]
    cards_needed = BURN_CARD_COUNT + board_card_count
    if len(hand.deck) < cards_needed:
        raise DeckEmptyError(
            f"The deck has {len(hand.deck)} cards but dealing the {next_street.value} needs {cards_needed}"
        )

    for _ in range(BURN_CARD_COUNT):
        hand.burned_cards.append(hand.deck.draw())
    for _ in range(board_card_count):
        hand.board.append(hand.deck.draw())
    hand.street = next_street
