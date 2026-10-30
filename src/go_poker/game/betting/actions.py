from dataclasses import dataclass
from enum import Enum


class InvalidActionError(ValueError):
    """Raised when an action is created with an amount its type does not allow."""


class ActionType(Enum):
    FOLD = "Fold"
    CHECK = "Check"
    CALL = "Call"
    BET = "Bet"
    RAISE = "Raise"


AMOUNT_ACTION_TYPES = (ActionType.BET, ActionType.RAISE)


@dataclass(frozen=True)
class Action:
    """A betting action. There is no separate all-in action; a call, bet or raise may use the whole stack.

    For BET and RAISE, `amount` is the target: the player's street contribution after the action ("bet to" /
    "raise to"), never the number of chips added. FOLD, CHECK and CALL carry no amount. Whether an amount is legal for
    the current hand is decided by the legal actions, not here.
    """

    type: ActionType
    amount: int | None = None

    def __post_init__(self) -> None:
        if self.type in AMOUNT_ACTION_TYPES:
            if self.amount is None or self.amount <= 0:
                raise InvalidActionError(f"{self.type.value} needs a positive target amount")
        elif self.amount is not None:
            raise InvalidActionError(f"{self.type.value} carries no amount")
