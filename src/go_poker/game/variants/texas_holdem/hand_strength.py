from collections.abc import Sequence
from itertools import accumulate

from go_poker.core.best_hand import BestHand, _best_hand
from go_poker.core.card import Card
from go_poker.core.evaluator import DuplicateCardsError, WrongCardAmountError, _best_fives
from go_poker.game.poker_hand import PokerHand
from go_poker.game.variants.texas_holdem.dealing import BOARD_CARD_COUNTS, HOLE_CARD_COUNT, InvalidHoleCardCountError

# The board sizes a Hold'em hand passes through: empty preflop, then after the flop, turn and river.
_BOARD_SIZES = (0, *accumulate(BOARD_CARD_COUNTS.values()))


class SeatNotInHandError(ValueError):
    """Raised when reading the hand strength of a seat that does not play in the hand."""


def holdem_hand_strength(hole_cards: Sequence[Card], board: Sequence[Card]) -> BestHand | None:
    """The best five-card hand of a Hold'em player's two hole cards and the board so far, or None for an empty board.

    `hole_cards` is in the order dealt and `board` in the order dealt. The `rank` is that of `evaluate_best` over the
    same cards. Among the five-card combinations of that rank, the one using the fewest hole cards is chosen, then the
    one whose cards were dealt earliest (board cards in dealt order, then hole cards in dealt order), so a board that
    plays is returned as it is. The cards come back in order of significance (see `BestHand`).

    Checked in this order, before anything is evaluated:
    1. the player must hold exactly HOLE_CARD_COUNT cards: `InvalidHoleCardCountError`, even preflop;
    2. the board must have 0, 3, 4 or 5 cards: `WrongCardAmountError`;
    3. no card may appear twice among the hole cards and the board: `DuplicateCardsError`, even preflop.
    Only then does an empty board give None. The inputs are never changed and the result holds fresh tuples.
    """
    hole = tuple(hole_cards)
    board_cards = tuple(board)
    if len(hole) != HOLE_CARD_COUNT:
        raise InvalidHoleCardCountError(f"Hand strength needs exactly {HOLE_CARD_COUNT} hole cards, got {len(hole)}")
    if len(board_cards) not in _BOARD_SIZES:
        raise WrongCardAmountError(
            f"A Hold'em board has {', '.join(map(str, _BOARD_SIZES))} cards, got {len(board_cards)}"
        )
    deal_order = (*board_cards, *hole)
    if len(set(deal_order)) != len(deal_order):
        raise DuplicateCardsError("The hole cards and the board contain duplicate cards")
    if not board_cards:
        return None

    rank, best_fives = _best_fives((*hole, *board_cards))
    position = {card: index for index, card in enumerate(deal_order)}

    def preference(combo: tuple[Card, ...]) -> tuple[int, tuple[int, ...]]:
        hole_count = sum(card in hole for card in combo)
        return hole_count, tuple(sorted(position[card] for card in combo))

    chosen = min(best_fives, key=preference)
    return _best_hand(rank, sorted(chosen, key=position.__getitem__))


def hand_strength(hand: PokerHand, seat: int) -> BestHand | None:
    """The current hand strength of a seat that plays in the hand: its best five from its hole cards and the board
    dealt so far, or None while the board is empty (see `holdem_hand_strength`).

    An unknown seat raises `SeatNotInHandError`. This is a read: it works for a folded, mucked or settled seat, ignores
    the betting, showdown and settlement, and never changes or stores anything. A seat that has not been dealt exactly
    HOLE_CARD_COUNT hole cards raises `InvalidHoleCardCountError`.
    """
    state = next((state for state in hand.players if state.seat_number == seat), None)
    if state is None:
        raise SeatNotInHandError(f"Seat {seat} does not play in this hand")
    return holdem_hand_strength(state.hole_cards, hand.board)
