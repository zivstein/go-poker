from go_poker.game.betting.state import BettingState
from go_poker.game.hand_state import HandPlayerState


def min_bet_target(betting: BettingState) -> int:
    """The smallest No-Limit bet target when nobody has bet on the street: the big blind."""
    return betting.stakes.big_blind


def min_raise_target(betting: BettingState) -> int:
    """The smallest No-Limit raise target: the current bet plus the last full raise size."""
    return betting.current_bet + betting.last_full_raise_size


def max_target(hand_player: HandPlayerState) -> int:
    """The largest No-Limit target: the player's street contribution plus their whole remaining stack."""
    return hand_player.street_contribution + hand_player.player.stack
