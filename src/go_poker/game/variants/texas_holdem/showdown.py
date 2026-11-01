from collections.abc import Collection

from go_poker.core.evaluator import evaluate_best
from go_poker.core.hand_rank import HandRank
from go_poker.game.betting.rounds import is_betting_closed, is_round_complete
from go_poker.game.betting.state import BettingNotInitializedError, BettingState
from go_poker.game.hand_history import HandSettled, ShowdownDecided, ShowdownStarted, _appended
from go_poker.game.poker_hand import PokerHand, _require_unsettled
from go_poker.game.settlement import _settle
from go_poker.game.showdown import Showdown, ShowdownAction, ShowdownKind, decision_order
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
    """Raised when starting a showdown for, or settling, a contested hand whose showdown is not yet certain: further
    betting is still possible."""


class UncontestedHandError(RuntimeError):
    """Raised when starting a showdown for a hand with fewer than two live players: an uncontested hand has no
    showdown."""


class ShowdownAlreadyStartedError(RuntimeError):
    """Raised when starting a showdown for a hand whose showdown has already started."""


class ShowdownNotStartedError(RuntimeError):
    """Raised when a showdown decision, or the settlement of a hand that needs a started showdown, comes before the
    showdown has started."""


class ShowdownIncompleteError(RuntimeError):
    """Raised when settling a hand whose started showdown still has pending decisions."""


def _require_complete_board(hand: PokerHand) -> None:
    if len(hand.board) != COMPLETE_BOARD_SIZE:
        raise IncompleteBoardError(
            f"A showdown needs a board of {COMPLETE_BOARD_SIZE} cards but the board has {len(hand.board)}"
        )


def _showdown_ranks(hand: PokerHand, seats: Collection[int]) -> dict[int, HandRank]:
    """The HandRank of exactly the given seats: the best five of their hole cards and the board, keyed by seat in hand
    order. Engine-internal; the public derived read is `hand_strength` (see `hand_strength.py`).

    The board must be complete and each of the given seats must hold exactly HOLE_CARD_COUNT hole cards; both are
    checked before anything is evaluated. No other player's hole cards are checked or evaluated, so a mucked or
    unshown hand is never touched. Which seats may be ranked, and whether the hand is ready to settle, is not checked
    here. The hand is never changed.
    """
    _require_complete_board(hand)

    states = [state for state in hand.players if state.seat_number in seats]
    if any(len(state.hole_cards) != HOLE_CARD_COUNT for state in states):
        raise InvalidHoleCardCountError(
            f"A showdown needs every ranked player to hold exactly {HOLE_CARD_COUNT} hole cards"
        )

    return {state.seat_number: evaluate_best([*state.hole_cards, *hand.board]) for state in states}


def _live_count(hand: PokerHand) -> int:
    return sum(not hand_player.folded for hand_player in hand.players)


def _showdown_kind(hand: PokerHand, betting: BettingState) -> ShowdownKind | None:
    """Classify a hand with at least two live players: None while further betting is still possible, else the kind of
    its showdown. Engine-internal: the one rule shared by `start_showdown` and `settle_hand`.

    The hand is ready when the current betting round is complete and either it is the river round or betting is closed
    (at most one player can still act). It is `ALL_IN` when any live player is all-in, else `INTERACTIVE`. All-in is
    read from the hand as it is, so a payout, which clears `all_in`, must not come before it. A closed round before the
    river with two or more live players always has a live all-in player, so it is always `ALL_IN`.
    """
    if not (is_round_complete(betting) and (betting.street is Street.RIVER or is_betting_closed(hand))):
        return None
    if any(hand_player.all_in and not hand_player.folded for hand_player in hand.players):
        return ShowdownKind.ALL_IN
    return ShowdownKind.INTERACTIVE


def _candidate_showdown(hand: PokerHand, betting: BettingState) -> Showdown | None:
    """The showdown a hand with at least two live players would start with now, or None when it is not ready (see
    `_showdown_kind`). Nothing is changed. Engine-internal: the one builder shared by `start_showdown` and
    `settle_hand`.

    `ALL_IN` lists every live seat in canonical order, with no aggressor and no decisions; `INTERACTIVE` is the river
    decision order, starting with the round's last aggressor, and has no decisions yet.
    """
    kind = _showdown_kind(hand, betting)
    if kind is None:
        return None
    seats = [hand_player.seat_number for hand_player in hand.players]
    live = {hand_player.seat_number for hand_player in hand.players if not hand_player.folded}
    last_aggressor = betting.last_aggressor if kind is ShowdownKind.INTERACTIVE else None
    return Showdown(kind, decision_order(seats, live, last_aggressor))


def start_showdown(hand: PokerHand) -> None:
    """Start the showdown of a Hold'em hand whose showdown is certain: record which live seats reach it, of which kind
    and in what decision order.

    Checked in this order, each rejection leaving the hand unchanged:
    1. an already settled hand: `HandAlreadySettledError`;
    2. the hand must have a betting state;
    3. a hand whose showdown has already started: `ShowdownAlreadyStartedError`;
    4. fewer than two live players: `UncontestedHandError`, since an uncontested hand has no showdown;
    5. further betting must no longer be possible: `ShowdownNotReadyError` otherwise (see `settle_hand`).
    Only `hand.showdown` is set, and `ShowdownStarted` (its kind and order) is recorded after it, for both kinds. It
    records seats, not cards, and neither the board nor any hole cards are checked, so a closed hand starts its showdown
    before its board is run out. Folded players never appear. An `ALL_IN` showdown lists every live seat clockwise from
    the first seat left of the button, the button last, and is complete from the start. An `INTERACTIVE` showdown, for a
    river round that completed with nobody all-in, starts with the river's last bettor or raiser, or with the first live
    seat left of the button when nobody bet, and goes clockwise; every live player then decides to show or muck (see
    `apply_showdown_action`).
    """
    _require_unsettled(hand)
    betting = hand.betting
    if betting is None:
        raise BettingNotInitializedError("Betting has not been initialized for this hand")
    if hand.showdown is not None:
        raise ShowdownAlreadyStartedError("The showdown of this hand has already started")
    if _live_count(hand) < 2:
        raise UncontestedHandError("An uncontested hand has no showdown to start")

    showdown = _candidate_showdown(hand, betting)
    if showdown is None:
        raise ShowdownNotReadyError("Further betting is still possible, so the showdown cannot start yet")
    hand.showdown = showdown
    hand.history = _appended(hand.history, ShowdownStarted(showdown.kind, showdown.order))


def apply_showdown_action(hand: PokerHand, seat: int, action: ShowdownAction) -> None:
    """Record `seat`'s SHOW or MUCK decision in the hand's started showdown.

    Checked in this order, each rejection leaving the hand unchanged:
    1. an already settled hand: `HandAlreadySettledError`;
    2. the showdown must have started: `ShowdownNotStartedError`;
    3. the showdown must be incomplete and `seat` its current decider: `NotShowdownTurnError` otherwise, which also
       covers every decision on an `ALL_IN` showdown;
    4. `action` must be a `ShowdownAction`: `TypeError` otherwise (checked by `Showdown.decide`, after the turn).
    Only `hand.showdown` changes, by one decision, and one `ShowdownDecided` is recorded after it. A muck is showdown
    state only: the seat is not folded and its contributions and the betting state are unchanged.
    """
    _require_unsettled(hand)
    if hand.showdown is None:
        raise ShowdownNotStartedError("The showdown of this hand has not started")
    hand.showdown = hand.showdown.decide(seat, action)
    hand.history = _appended(hand.history, ShowdownDecided(seat, action))


def settle_hand(hand: PokerHand) -> None:
    """Settle a Hold'em hand that has reached its end: pay the winners and store the hand's settlement.

    Checked in this order, each rejection leaving the hand unchanged:
    1. an already settled hand is rejected first, because paying out can clear `all_in` and make betting look open
       again;
    2. the hand must have a betting state;
    3. a hand with exactly one live player is settled uncontested on any street, without evaluating anything and
       without recording a showdown;
    4. otherwise the board must be complete;
    5. and no further betting may be possible: the current betting round is complete and either it is the river round
       or betting is closed (at most one player can still act). A river dealt without its round started, or a river
       round in progress, is not ready;
    6. the showdown must be complete: an `INTERACTIVE` hand without a started showdown raises
       `ShowdownNotStartedError`, and one with pending decisions raises `ShowdownIncompleteError`. A contested `ALL_IN`
       hand with no showdown yet is not rejected: its complete showdown is built from the hand as it is before the
       payout, because the payout clears `all_in`.
    Only the shown hands are then evaluated, and only their hole cards are checked (see `_showdown_ranks`). Each pot is
    awarded among its eligible seats that are still contenders: a mucked seat is never paid, and a last contender who
    won without showing needs no rank. `Settlement.showdown_ranks` holds the shown seats only.

    The built `ALL_IN` showdown is stored only after the settlement succeeds, so a rejection leaves `hand.showdown`
    unset. An existing showdown is kept as it is. An uncontested hand never records a showdown.

    `HandSettled` is recorded once, after every mutation, in a single history assignment. A contested `ALL_IN` hand
    with no showdown yet also records `ShowdownStarted` (its built showdown) just before it, since every contested
    hand's history holds its showdown start. An existing showdown has already recorded its start, so no second one is
    recorded; an uncontested hand records `HandSettled` alone. A rejection records nothing.
    """
    _require_unsettled(hand)
    betting = hand.betting
    if betting is None:
        raise BettingNotInitializedError("Betting has not been initialized for this hand")

    live = {hand_player.seat_number for hand_player in hand.players if not hand_player.folded}
    if len(live) == 1:
        settlement = _settle(hand, {}, live)
        hand.history = _appended(hand.history, HandSettled(settlement))
        return

    _require_complete_board(hand)
    candidate = _candidate_showdown(hand, betting)
    if candidate is None:
        raise ShowdownNotReadyError("Further betting is still possible, so the hand cannot be settled yet")

    showdown = hand.showdown
    started = showdown is not None
    if showdown is None:
        if candidate.kind is ShowdownKind.INTERACTIVE:
            raise ShowdownNotStartedError(
                "The showdown of this hand has not started, so the hand cannot be settled yet"
            )
        showdown = candidate
    elif not showdown.is_complete:
        raise ShowdownIncompleteError("The showdown has pending decisions, so the hand cannot be settled yet")

    settlement = _settle(hand, _showdown_ranks(hand, showdown.shown), showdown.contenders)
    hand.showdown = showdown
    history = hand.history
    if not started:
        history = _appended(history, ShowdownStarted(showdown.kind, showdown.order))
    hand.history = _appended(history, HandSettled(settlement))
