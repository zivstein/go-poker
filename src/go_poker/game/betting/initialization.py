from go_poker.game.betting.chips import commit_chips
from go_poker.game.betting.collection import collect_round
from go_poker.game.betting.rounds import first_pending_after, is_round_complete, pending_at_round_start
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingState
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.poker_hand import PokerHand, _require_unsettled
from go_poker.game.position import Blind
from go_poker.game.street import Street


class BettingAlreadyInitializedError(RuntimeError):
    """Raised when initializing betting for a hand that already has a betting state."""


class BettingNotPreflopError(RuntimeError):
    """Raised when initializing betting for a hand that is no longer on the preflop street."""


def _blind_player(hand: PokerHand, blind: Blind) -> HandPlayerState:
    return next(hand_player for hand_player in hand.players if hand_player.blind is blind)


def initialize_betting(hand: PokerHand, stakes: Stakes) -> None:
    """Post the blinds and attach the hand's preflop betting state.

    The small blind and big blind post real chips: each posts their blind, or their whole stack when it is smaller (a
    short blind), and posting the last chips marks that player all-in. The current bet and last full raise size start
    at the full big blind, whatever the blinds actually posted. Posting a blind is not an action, so nobody has acted
    yet (`acted_at_bet` is empty) and there is no `last_aggressor`. Every eligible player, blinds included, is pending
    (subject to the round's early endings, see `settle_pending`), and the first pending player clockwise after the big
    blind acts first. When those endings leave nobody pending, the preflop round is complete as soon as the blinds are
    posted and is collected at once (see `collect_round`), so the part of a blind that nobody can match goes back to
    its player.

    A settled hand is rejected first (`HandAlreadySettledError`), before any other validation. A hand that already has
    betting or is no longer preflop is then rejected before anything changes, leaving it unchanged.
    Blind stacks are not checked: hands contain only players who start with chips (the start-of-hand chip rule), so
    every blind posts a positive amount.
    """
    _require_unsettled(hand)
    if hand.betting is not None:
        raise BettingAlreadyInitializedError("Betting has already been initialized for this hand")

    if hand.street is not Street.PREFLOP:
        raise BettingNotPreflopError(f"Betting is initialized preflop, but the hand is on the {hand.street.value}")

    small_blind_player = _blind_player(hand, Blind.SMALL)
    big_blind_player = _blind_player(hand, Blind.BIG)
    # Not validated: hands contain only players who start with chips, so every blind posts a positive amount.
    for hand_player, amount in ((small_blind_player, stakes.small_blind), (big_blind_player, stakes.big_blind)):
        commit_chips(hand_player, min(amount, hand_player.player.stack))

    pending = pending_at_round_start(hand.players, stakes.big_blind)
    hand.betting = BettingState(
        street=Street.PREFLOP,
        stakes=stakes,
        current_bet=stakes.big_blind,
        last_full_raise_size=stakes.big_blind,
        current_actor=first_pending_after(hand.players, big_blind_player.seat_number, pending),
        pending_actors=pending,
        acted_at_bet={},
        last_aggressor=None,
    )
    if is_round_complete(hand.betting):
        collect_round(hand.players)
