from go_poker.game.betting.state import BettingNotInitializedError, BettingState
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.poker_hand import PokerHand, _require_unsettled


class BettingRoundNotCompleteError(RuntimeError):
    """Raised when starting a betting round while the previous round still has players to act."""


class BettingRoundAlreadyStartedError(RuntimeError):
    """Raised when starting a betting round for the street the betting state already belongs to."""


def is_eligible(hand_player: HandPlayerState) -> bool:
    """An eligible player can still take a betting action: they have neither folded nor gone all-in."""
    return not hand_player.folded and not hand_player.all_in


def is_round_complete(betting: BettingState) -> bool:
    """A betting round is complete when nobody owes an action, so nobody is to act."""
    return not betting.pending_actors


def can_opponent_respond(players: tuple[HandPlayerState, ...], hand_player: HandPlayerState) -> bool:
    """Whether another player could still respond to the player: one who has neither folded nor gone all-in."""
    return any(is_eligible(other) for other in players if other is not hand_player)


def call_target(players: tuple[HandPlayerState, ...], hand_player: HandPlayerState, current_bet: int) -> int:
    """The street contribution the player must reach to call: what the other live players can actually contest.

    While an opponent can still respond (see `can_opponent_respond`), it is the nominal current bet. Otherwise it is
    the largest street contribution among the other live players (0 when there are none), never above the current
    bet, so the player is never asked to commit chips that nobody can match. The current bet itself keeps its nominal
    value.
    """
    if can_opponent_respond(players, hand_player):
        return current_bet
    live_opponents = [other for other in players if other is not hand_player and not other.folded]
    return min(current_bet, max((opponent.street_contribution for opponent in live_opponents), default=0))


def settle_pending(players: tuple[HandPlayerState, ...], pending: set[int], current_bet: int) -> set[int]:
    """Return who still owes an action once the round's early endings are applied.

    When only one player has not folded, the round is over and nobody is pending. When at most one player can still
    act, no opponent can respond, so only an eligible player who is still below their call target (see `call_target`)
    stays pending; otherwise the round is complete without a meaningless check.
    """
    live = [hand_player for hand_player in players if not hand_player.folded]
    if len(live) <= 1:
        return set()

    eligible = [hand_player for hand_player in live if is_eligible(hand_player)]
    if len(eligible) <= 1:
        return {
            hand_player.seat_number
            for hand_player in eligible
            if hand_player.seat_number in pending
            and hand_player.street_contribution < call_target(players, hand_player, current_bet)
        }
    return set(pending)


def pending_at_round_start(players: tuple[HandPlayerState, ...], current_bet: int) -> set[int]:
    """Return the seat numbers that owe an action when a betting round starts: every eligible player, after the
    round's early endings (see `settle_pending`)."""
    eligible = {hand_player.seat_number for hand_player in players if is_eligible(hand_player)}
    return settle_pending(players, eligible, current_bet)


def is_betting_closed(hand: PokerHand) -> bool:
    """Whether no further betting is possible in the hand. Derived on request, never stored.

    True when the current betting round is complete and at most one player can still act (has neither folded nor gone
    all-in): every live player is all-in, one live player with chips owes nothing and faces only all-in opponents, or
    everyone else has folded. No later round can then ask anyone to act. The betting layer does not know the variant's
    street sequence, so with two or more players able to act it is False even on the river.
    """
    betting = hand.betting
    if betting is None:
        raise BettingNotInitializedError("Betting has not been initialized for this hand")
    able_to_act = [hand_player for hand_player in hand.players if is_eligible(hand_player)]
    return is_round_complete(betting) and len(able_to_act) <= 1


def first_pending_after(players: tuple[HandPlayerState, ...], anchor_seat_number: int, pending: set[int]) -> int | None:
    """Return the first pending seat clockwise after the anchor seat, or None when nobody is pending.

    `players` is ordered clockwise from the button, so the search follows that order and wraps around it.
    """
    seats = [hand_player.seat_number for hand_player in players]
    anchor_index = seats.index(anchor_seat_number)
    clockwise_after_anchor = seats[anchor_index + 1 :] + seats[: anchor_index + 1]
    return next((seat_number for seat_number in clockwise_after_anchor if seat_number in pending), None)


def start_betting_round(hand: PokerHand) -> None:
    """Start the betting round for the street the dealing layer has moved the hand to.

    A settled hand is rejected first (`HandAlreadySettledError`), before any other validation, because a payout can
    clear `all_in` and make a new round look startable. The previous round must be complete and the hand must be on
    a different street than the betting state; the street sequence itself belongs to the variant's dealing rules and
    is not checked here. A completed round has already been collected (see `collect_round`), so nobody has chips in
    front. The current bet is zero, the last full raise size returns to the big blind, and nobody has acted yet, so
    `acted_at_bet` is cleared. Every eligible player is pending, and the first pending player clockwise after the
    button acts first, so heads-up the big blind acts first. A rejection leaves the hand unchanged.
    """
    _require_unsettled(hand)
    betting = hand.betting
    if betting is None:
        raise BettingNotInitializedError("Betting has not been initialized for this hand")
    if not is_round_complete(betting):
        raise BettingRoundNotCompleteError(f"The {betting.street.value} betting round still has players to act")
    if hand.street is betting.street:
        raise BettingRoundAlreadyStartedError(f"The {hand.street.value} betting round has already started")

    betting.street = hand.street
    betting.current_bet = 0
    betting.last_full_raise_size = betting.stakes.big_blind
    betting.acted_at_bet = {}
    betting.pending_actors = pending_at_round_start(hand.players, current_bet=0)
    # Players are ordered clockwise from the button, so the button is the first of them.
    betting.current_actor = first_pending_after(hand.players, hand.players[0].seat_number, betting.pending_actors)
