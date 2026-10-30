from dataclasses import dataclass

from go_poker.game.betting.stakes import Stakes
from go_poker.game.street import Street


class BettingNotInitializedError(RuntimeError):
    """Raised when a betting operation needs the hand's betting state but betting has not been initialized."""


@dataclass
class BettingState:
    """The progress of one hand's betting, for the street its current or completed betting round belongs to.

    Players are identified by seat number, which is unique within a hand. `current_actor` is None when nobody is to
    act. `pending_actors` holds only the players who still owe an action in the round; whether a player may bet or
    raise is derived separately from `acted_at_bet` (see `has_raise_rights`). Legal actions are never stored; they are
    derived from the hand state.
    """

    street: Street
    stakes: Stakes
    # The nominal betting target: the street contribution a fully funded player must match. No street contribution is
    # ever above it, but it is not guaranteed to equal the highest one (a short all-in blind or call stays below it).
    current_bet: int
    # The size of the last full bet or raise: the big blind when a round starts, changed only by a full bet or raise and
    # never by a short all-in.
    last_full_raise_size: int
    current_actor: int | None
    pending_actors: set[int]
    # Seat number -> the current bet right after that seat's latest action in the current round. Only seats that have
    # acted have an entry; posting a blind is not an action. Cleared whenever a betting round starts.
    acted_at_bet: dict[int, int]
