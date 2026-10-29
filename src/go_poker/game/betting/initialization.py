from go_poker.game.betting.chips import commit_chips
from go_poker.game.betting.round_start import first_pending_after, pending_at_round_start
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingState
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind
from go_poker.game.street import Street


class BettingAlreadyInitializedError(RuntimeError):
    """Raised when initializing betting for a hand that already has a betting state."""


class BettingNotPreflopError(RuntimeError):
    """Raised when initializing betting for a hand that is no longer on the preflop street."""


class ShortBlindAllInNotSupportedError(RuntimeError):
    """Raised when a blind player's stack is smaller than their blind.

    The player is valid: in poker they would post their whole stack and be all-in for less than the blind. That short
    blind all-in is intentionally unsupported in Milestone 2 and deferred to Milestone 3, together with pots.
    """


def _blind_player(hand: PokerHand, blind: Blind) -> HandPlayerState:
    return next(hand_player for hand_player in hand.players if hand_player.blind is blind)


def initialize_betting(hand: PokerHand, stakes: Stakes) -> None:
    """Post the blinds and attach the hand's preflop betting state.

    The small blind and big blind post in full as real chips; posting the last chips marks that player all-in. The
    current bet and last full raise size start at the big blind. Posting a blind is not an action, so every eligible
    player, blinds included, is pending, and the first pending player clockwise after the big blind acts first. The hand
    must be preflop without betting yet; it is validated before anything changes, so a rejection leaves it unchanged.
    """
    if hand.betting is not None:
        raise BettingAlreadyInitializedError("Betting has already been initialized for this hand")

    if hand.street is not Street.PREFLOP:
        raise BettingNotPreflopError(f"Betting is initialized preflop, but the hand is on the {hand.street.value}")

    small_blind_player = _blind_player(hand, Blind.SMALL)
    big_blind_player = _blind_player(hand, Blind.BIG)
    for hand_player, amount in ((small_blind_player, stakes.small_blind), (big_blind_player, stakes.big_blind)):
        if hand_player.player.stack < amount:
            raise ShortBlindAllInNotSupportedError(
                f"Seat {hand_player.seat_number} has {hand_player.player.stack} chips for a {hand_player.blind} of "
                f"{amount}; short blind all-ins are not supported until Milestone 3"
            )

    commit_chips(small_blind_player, stakes.small_blind)
    commit_chips(big_blind_player, stakes.big_blind)

    pending = pending_at_round_start(hand.players, stakes.big_blind)
    hand.betting = BettingState(
        street=Street.PREFLOP,
        stakes=stakes,
        current_bet=stakes.big_blind,
        last_full_raise_size=stakes.big_blind,
        current_actor=first_pending_after(hand.players, big_blind_player.seat_number, pending),
        pending_actors=pending,
    )
