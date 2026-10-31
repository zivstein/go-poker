from go_poker.core.evaluator import evaluate_best
from go_poker.core.hand_rank import HandRank
from go_poker.game.betting.rounds import is_betting_closed, is_round_complete
from go_poker.game.betting.state import BettingNotInitializedError, BettingState
from go_poker.game.poker_hand import PokerHand, _require_unsettled
from go_poker.game.reveal import Reveal, RevealKind, show_order
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
    """Raised when revealing or settling a contested hand whose showdown is not yet certain: further betting is still
    possible."""


class UncontestedHandError(RuntimeError):
    """Raised when revealing a hand with fewer than two live players: an uncontested hand has no showdown."""


class HandAlreadyRevealedError(RuntimeError):
    """Raised when revealing a hand that has already been revealed."""


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


def _live_count(hand: PokerHand) -> int:
    return sum(not hand_player.folded for hand_player in hand.players)


def _reveal_kind(hand: PokerHand, betting: BettingState) -> RevealKind | None:
    """Classify a hand with at least two live players: None while further betting is still possible, else the kind of
    its reveal. Engine-internal: the one rule shared by `reveal_hands` and `settle_hand`.

    The hand is ready when the current betting round is complete and either it is the river round or betting is closed
    (at most one player can still act). It is `ALL_IN` when any live player is all-in, else `SHOWDOWN`. All-in is read
    from the hand as it is, so a payout, which clears `all_in`, must not come before it. A closed round before the
    river with two or more live players always has a live all-in player, so it is always `ALL_IN`.
    """
    if not (is_round_complete(betting) and (betting.street is Street.RIVER or is_betting_closed(hand))):
        return None
    if any(hand_player.all_in and not hand_player.folded for hand_player in hand.players):
        return RevealKind.ALL_IN
    return RevealKind.SHOWDOWN


def _candidate_reveal(hand: PokerHand, betting: BettingState) -> Reveal | None:
    """The reveal a hand with at least two live players would record now, or None when it is not ready (see
    `_reveal_kind`). Nothing is changed. Engine-internal: the one builder shared by `reveal_hands` and `settle_hand`.

    `ALL_IN` lists every live seat in canonical order, with no aggressor; `SHOWDOWN` is the river show order, starting
    with the round's last aggressor.
    """
    kind = _reveal_kind(hand, betting)
    if kind is None:
        return None
    seats = [hand_player.seat_number for hand_player in hand.players]
    live = {hand_player.seat_number for hand_player in hand.players if not hand_player.folded}
    last_aggressor = betting.last_aggressor if kind is RevealKind.SHOWDOWN else None
    return Reveal(kind, show_order(seats, live, last_aggressor))


def reveal_hands(hand: PokerHand) -> None:
    """Reveal a Hold'em hand whose showdown is certain: record which live seats are revealed, and in what order.

    Checked in this order, each rejection leaving the hand unchanged:
    1. an already settled hand: `HandAlreadySettledError`;
    2. the hand must have a betting state;
    3. a hand that is already revealed: `HandAlreadyRevealedError`;
    4. fewer than two live players: `UncontestedHandError`, since an uncontested hand has no showdown;
    5. further betting must no longer be possible: `ShowdownNotReadyError` otherwise (see `settle_hand`).
    Only `hand.reveal` is set. It records seats, not cards, and the board is not checked, so a closed hand is
    revealed before its board is run out. Folded players are never revealed. The `ALL_IN` reveal lists every live seat
    clockwise from the first seat left of the button, the button last. The `SHOWDOWN` reveal, for a river round that
    completed with nobody all-in, starts with the river's last bettor or raiser, or with the first live seat left of
    the button when nobody bet, and goes clockwise.
    """
    _require_unsettled(hand)
    betting = hand.betting
    if betting is None:
        raise BettingNotInitializedError("Betting has not been initialized for this hand")
    if hand.reveal is not None:
        raise HandAlreadyRevealedError("This hand has already been revealed")
    if _live_count(hand) < 2:
        raise UncontestedHandError("An uncontested hand has no showdown to reveal")

    reveal = _candidate_reveal(hand, betting)
    if reveal is None:
        raise ShowdownNotReadyError("Further betting is still possible, so the hand cannot be revealed yet")
    hand.reveal = reveal


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

    A contested hand that is not yet revealed is revealed by the settlement (see `reveal_hands`): the reveal is built
    from the hand as it is before the payout, and stored only after the settlement succeeds, so a rejection leaves
    `hand.reveal` unset. An existing reveal is kept as it is. An uncontested hand is never revealed.
    """
    _require_unsettled(hand)
    betting = hand.betting
    if betting is None:
        raise BettingNotInitializedError("Betting has not been initialized for this hand")

    if _live_count(hand) == 1:
        _settle(hand, {})
        return

    _require_complete_board(hand)
    reveal = _candidate_reveal(hand, betting)
    if reveal is None:
        raise ShowdownNotReadyError("Further betting is still possible, so the hand cannot be settled yet")

    ranks = showdown_ranks(hand)
    _settle(hand, ranks)
    if hand.reveal is None:
        hand.reveal = reveal
