from go_poker.core.deck import DeckEmptyError
from go_poker.game.poker_hand import PokerHand

HOLE_CARD_COUNT = 2


class HoleCardsAlreadyDealtError(RuntimeError):
    """Raised when dealing hole cards to a hand in which a participant already holds hole cards."""


def deal_hole_cards(hand: PokerHand) -> None:
    """Deal HOLE_CARD_COUNT cards to every participant from the hand's deck, one card per player per round.

    Each round starts with the player clockwise of the button and ends with the button. No card is burned.
    The hand is validated before any card is drawn, so a failure leaves it unchanged.
    """
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
