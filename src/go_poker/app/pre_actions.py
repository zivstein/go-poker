"""Betting pre-actions: what a member may pre-select while it is not their turn (ADR 0006 §5).

Values only. When the turn arrives the application submits a normal engine action; this module decides nothing about
poker.
"""

from dataclasses import dataclass
from enum import Enum


class PreActionKind(Enum):
    CHECK = "check"
    CHECK_OR_FOLD = "check_or_fold"
    FOLD = "fold"
    CALL_CURRENT = "call_current"  # a call of exactly the chips owed when it was offered


@dataclass(frozen=True)
class PreAction:
    """A pre-action. `amount` is the chips owed that a `CALL_CURRENT` is for (a positive integer), and None for every
    other kind."""

    kind: PreActionKind
    amount: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PreActionKind):
            raise ValueError("The pre-action kind must be a PreActionKind")
        if self.kind is PreActionKind.CALL_CURRENT:
            if isinstance(self.amount, bool) or not isinstance(self.amount, int) or self.amount <= 0:
                raise ValueError("A CALL_CURRENT pre-action needs a positive integer amount")
        elif self.amount is not None:
            raise ValueError(f"A {self.kind.name} pre-action has no amount")
