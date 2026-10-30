from go_poker.core.evaluator import evaluate_best
from go_poker.core.hand_rank import HandRank
from go_poker.game.poker_hand import PokerHand
from go_poker.game.variants.texas_holdem.dealing import (
    BOARD_CARD_COUNTS,
    HOLE_CARD_COUNT,
    InvalidHoleCardCountError,
)

COMPLETE_BOARD_SIZE = sum(BOARD_CARD_COUNTS.values())


class IncompleteBoardError(RuntimeError):
    """Raised when evaluating a showdown before the whole board has been dealt."""


def showdown_ranks(hand: PokerHand) -> dict[int, HandRank]:
    """Each live player's HandRank: the best five of their hole cards and the board, keyed by seat in hand order.

    Folded players are excluded. The board must be complete and every live player must hold exactly HOLE_CARD_COUNT
    hole cards; both are checked before anything is evaluated. Whether the hand is ready to settle by its betting
    state is not checked here. The hand is never changed.
    """
    if len(hand.board) != COMPLETE_BOARD_SIZE:
        raise IncompleteBoardError(
            f"A showdown needs a board of {COMPLETE_BOARD_SIZE} cards but the board has {len(hand.board)}"
        )

    live_players = [state for state in hand.players if not state.folded]
    if any(len(state.hole_cards) != HOLE_CARD_COUNT for state in live_players):
        raise InvalidHoleCardCountError(
            f"A showdown needs every live player to hold exactly {HOLE_CARD_COUNT} hole cards"
        )

    return {state.seat_number: evaluate_best([*state.hole_cards, *hand.board]) for state in live_players}
