"""What a member sees of the table: one frozen `TableView`, composed from the engine's Hold'em view.

No view carries a `UserId` (or a `player_id`): seats are identified by number and display name only.
"""

from dataclasses import dataclass
from enum import Enum

from go_poker.app.identity import DisplayName
from go_poker.app.pre_actions import PreAction
from go_poker.game.betting.stakes import Stakes
from go_poker.game.variants.texas_holdem.view import HoldemView


class TablePhase(Enum):
    NOT_STARTED = "not_started"
    HAND_IN_PROGRESS = "hand_in_progress"
    HAND_COMPLETE = "hand_complete"
    WAITING_FOR_PLAYERS = "waiting_for_players"


@dataclass(frozen=True)
class TableSettings:
    """A table's stakes, the buy-in every member sits with, and its seat count (2-9, checked by the engine's table)."""

    stakes: Stakes
    buy_in: int
    max_seats: int

    def __post_init__(self) -> None:
        if isinstance(self.buy_in, bool) or not isinstance(self.buy_in, int) or self.buy_in <= 0:
            raise ValueError("The buy-in must be a positive integer")


@dataclass(frozen=True)
class SessionSeatView:
    """One seat's owner at the application level; `display_name` is None for an empty seat."""

    number: int
    display_name: DisplayName | None
    is_host: bool


@dataclass(frozen=True)
class YouView:
    """The viewer's own seat, host flag and private intents. The intents are private to the viewer.

    `pre_action` is the viewer's selected pre-action as presented (a selected `CHECK_OR_FOLD` presents as `FOLD` while
    chips are owed), None when nothing is selected. `pre_action_options` are the pre-actions the viewer may select now,
    empty when none is available (not a participant, their own turn, folded, all-in, no open betting round, a pending
    leave).
    """

    seat: int
    is_host: bool
    pending_leave: bool
    pending_sit_out: bool
    pre_action: PreAction | None
    pre_action_options: tuple[PreAction, ...]


@dataclass(frozen=True)
class TableView:
    revision: int
    table_id: str
    code: str
    settings: TableSettings
    phase: TablePhase
    seats: tuple[SessionSeatView, ...]
    game: HoldemView
    you: YouView
