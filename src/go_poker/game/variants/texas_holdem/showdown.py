from go_poker.core.evaluator import evaluate_best
from go_poker.core.hand_rank import HandRank
from go_poker.game.betting.rounds import is_betting_closed, is_round_complete
from go_poker.game.betting.state import BettingNotInitializedError
from go_poker.game.poker_hand import PokerHand, _require_unsettled
from go_poker.game.settlement import _settle
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import (
    BOARD_CARD_COUNTS,
    HOLE_CARD_COUNT,
    InvalidHoleCardCountError,
)

COMPLETE_BOARD_SIZE = sum(BOARD_CARD_COUNTS.values())


class IncompleteBoardError(RuntimeError):
    """Raised when evaluating a showdown before the whole board has been dealt."""


class ShowdownNotReadyError(RuntimeError):
    """Raised when settling a contested hand while further betting is still possible."""


def _require_complete_board(hand: PokerHand) -> None:
    if len(hand.board) != COMPLETE_BOARD_SIZE:
        raise IncompleteBoardError(
            f"A showdown needs a board of {COMPLETE_BOARD_SIZE} cards but the board has {len(hand.board)}"
        )


def showdown_ranks(hand: PokerHand) -> dict[int, HandRank]:
    """Each live player's HandRank: the best five of their hole cards and the board, keyed by seat in hand order.

    Folded players are excluded. The board must be complete and every live player must hold exactly HOLE_CARD_COUNT
    hole cards; both are checked before anything is evaluated. Whether the hand is ready to settle by its betting
    state is not checked here. The hand is never changed.
    """
    _require_complete_board(hand)

    live_players = [state for state in hand.players if not state.folded]
    if any(len(state.hole_cards) != HOLE_CARD_COUNT for state in live_players):
        raise InvalidHoleCardCountError(
            f"A showdown needs every live player to hold exactly {HOLE_CARD_COUNT} hole cards"
        )

    return {state.seat_number: evaluate_best([*state.hole_cards, *hand.board]) for state in live_players}


def settle_hand(hand: PokerHand) -> None:
    """Settle a Hold'em hand that has reached its end: pay the winners and store the hand's settlement.

    Checked in this order, each rejection leaving the hand unchanged:
    1. an already settled hand is rejected first, because paying out can clear `all_in` and make betting look open
       again;
    2. the hand must have a betting state;
    3. a hand with exactly one live player is settled uncontested on any street, without evaluating anything;
    4. otherwise the board must be complete;
    5. and no further betting may be possible: the current betting round is complete and either it is the river round
       or betting is closed (at most one player can still act). A river dealt without its round started, or a river
       round in progress, is not ready.
    Every live player then competes for every pot they are eligible for (see `showdown_ranks`).
    """
    _require_unsettled(hand)
    betting = hand.betting
    if betting is None:
        raise BettingNotInitializedError("Betting has not been initialized for this hand")

    if sum(not hand_player.folded for hand_player in hand.players) == 1:
        _settle(hand, {})
        return

    _require_complete_board(hand)
    if not (is_round_complete(betting) and (betting.street is Street.RIVER or is_betting_closed(hand))):
        raise ShowdownNotReadyError("Further betting is still possible, so the hand cannot be settled yet")

    _settle(hand, showdown_ranks(hand))
