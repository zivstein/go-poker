from dataclasses import dataclass

from go_poker.game.betting.stakes import Stakes
from go_poker.game.street import Street


class BettingNotInitializedError(RuntimeError):
    """Raised when a betting operation needs the hand's betting state but betting has not been initialized."""


@dataclass
class BettingState:
    """The progress of one hand's betting, for the street its current or completed betting round belongs to.

    Players are identified by seat number, which is unique within a hand. `current_actor` is None when nobody is to
    act, and `pending_actors` holds the players who still owe an action in the round. Legal actions are never stored;
    they are derived from the hand state.
    """

    street: Street
    stakes: Stakes
    # The street contribution every remaining player must match.
    current_bet: int
    last_full_raise_size: int
    current_actor: int | None
    pending_actors: set[int]
