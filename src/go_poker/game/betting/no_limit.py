from go_poker.game.betting.state import BettingState
from go_poker.game.hand_state import HandPlayerState


def min_bet_target(betting: BettingState) -> int:
    """The smallest full No-Limit bet target when nobody has bet on the street: the big blind."""
    return betting.stakes.big_blind


def min_raise_target(betting: BettingState) -> int:
    """The smallest full No-Limit raise target: the current bet plus the last full raise size."""
    return betting.current_bet + betting.last_full_raise_size


def max_target(hand_player: HandPlayerState) -> int:
    """The largest No-Limit target, the player's all-in target: their street contribution plus their whole stack."""
    return hand_player.street_contribution + hand_player.player.stack


def has_raise_rights(betting: BettingState, seat_number: int) -> bool:
    """The No-Limit reopening rule: whether the seat may bet or raise, independent of whether it still owes an action.

    A player has raise rights when they have not acted in the current round, or when the current bet has risen by at
    least one full raise (`last_full_raise_size`) since their latest action. A check counts as acting; posting a blind
    does not. Because the increase is measured from the player's latest action, several short all-ins that together
    reach a full raise reopen raising, while a single short all-in below a full raise does not.
    """
    acted_at = betting.acted_at_bet.get(seat_number)
    return acted_at is None or betting.current_bet - acted_at >= betting.last_full_raise_size
