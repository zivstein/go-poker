"""Command results and shared transitions, all plain values (ADR 0006).

A command returns `Accepted` or `Rejected`; a rejection is a value and changes nothing. An accepted command may carry
several shared transitions, each with the revision it produced and every member's view captured right after it.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from go_poker.app.identity import UserId
from go_poker.app.views import TableView


class RejectionCode(Enum):
    STALE_REVISION = "stale_revision"
    NOT_A_MEMBER = "not_a_member"
    ALREADY_MEMBER = "already_member"
    LEFT_TABLE = "left_table"
    DISPLAY_NAME_TAKEN = "display_name_taken"
    SEAT_TAKEN = "seat_taken"
    INVALID_SEAT = "invalid_seat"
    NOT_HOST = "not_host"
    GAME_ALREADY_STARTED = "game_already_started"
    NOT_ENOUGH_PLAYERS = "not_enough_players"
    NO_HAND_IN_PROGRESS = "no_hand_in_progress"
    NOT_YOUR_TURN = "not_your_turn"
    ILLEGAL_ACTION = "illegal_action"
    LEAVE_PENDING = "leave_pending"
    NO_CHANGE = "no_change"
    NOT_AT_HAND_BOUNDARY = "not_at_hand_boundary"
    PRE_ACTION_UNAVAILABLE = "pre_action_unavailable"


class TransitionCause(Enum):
    """Why a shared transition happened."""

    COMMAND = "command"  # the requester's own shared change
    LEAVE_AUTO_ACTION = "leave_auto_action"  # the automatic action of a player with a pending leave
    PRE_ACTION = "pre_action"  # a pre-action executing when its owner's turn arrived
    HAND_BOUNDARY = "hand_boundary"  # `advance_hand`
    RESUME = "resume"  # a hand started and/or the engine generation was replaced while waiting


@dataclass(frozen=True)
class Transition:
    """One successful shared change: its revision, its cause, and every current member's full view right after it."""

    revision: int
    cause: TransitionCause
    views: Mapping[UserId, TableView]


@dataclass(frozen=True)
class Accepted:
    """An accepted command.

    `transitions` are its shared transitions in order (none for a private-only command). `view` is the requester's view
    after the whole command, or None for `advance_hand` and when the requester has just left.
    """

    transitions: tuple[Transition, ...]
    view: TableView | None


@dataclass(frozen=True)
class Rejected:
    code: RejectionCode
    message: str


type CommandResult = Accepted | Rejected
