from collections.abc import Collection, Sequence
from dataclasses import dataclass, replace
from enum import Enum


class ShowdownKind(Enum):
    """How a hand's live players reach showdown: all hands tabled at once because of an all-in, or an interactive river
    showdown where players decide in turn."""

    ALL_IN = "all_in"
    INTERACTIVE = "interactive"


class ShowdownAction(Enum):
    """A decision in an interactive showdown: reveal the hand and stay in contention, or give up without revealing."""

    SHOW = "show"
    MUCK = "muck"


class NotShowdownTurnError(RuntimeError):
    """Raised when a showdown decision comes from a seat that is not the current decider, or the showdown is already
    complete (an `ALL_IN` showdown always is)."""


@dataclass(frozen=True)
class Showdown:
    """The immutable record of a hand's showdown: the live seats that reach it and the decisions made so far.

    It records seats and decisions, not cards. `order` holds the live seats when the showdown starts and never
    changes. For `ShowdownKind.ALL_IN` every live hand is tabled at once, so `order` is canonical seat order (see
    `canonical_seat_order`), which is storage order only and not a sequence, and there are no decisions. For
    `ShowdownKind.INTERACTIVE` `order` is the decision order (see `decision_order`) and `decisions[i]` is the
    decision of `order[i]`. Folded seats never appear.

    Shown seats, mucked seats, contenders, the current decider and completion are derived from `order` and `decisions`,
    never stored. For `ALL_IN` every seat is shown and a contender. Otherwise the shown seats are those that decided
    SHOW, the mucked seats those that decided MUCK, and the contenders every seat in `order` that has not mucked,
    undecided seats included. An interactive showdown is complete once every seat has decided or only one contender
    remains; that last contender is not asked to decide.

    The record is not validated on construction. Engine-owned state produced through the supported operations is
    well-formed: the Hold'em `start_showdown` creates the initial valid record and `decide` produces each later valid
    one. Directly constructing a record or injecting invalid hand state is outside that contract; validating
    externally reconstructed or persisted state belongs at that external boundary when there is one.
    """

    kind: ShowdownKind
    order: tuple[int, ...]
    decisions: tuple[ShowdownAction, ...] = ()

    @property
    def shown(self) -> tuple[int, ...]:
        """The seats whose hands are shown, in `order`."""
        if self.kind is ShowdownKind.ALL_IN:
            return self.order
        return tuple(
            seat for seat, action in zip(self.order, self.decisions, strict=False) if action is ShowdownAction.SHOW
        )

    @property
    def mucked(self) -> tuple[int, ...]:
        """The seats that decided to muck, in `order`."""
        return tuple(
            seat for seat, action in zip(self.order, self.decisions, strict=False) if action is ShowdownAction.MUCK
        )

    @property
    def contenders(self) -> tuple[int, ...]:
        """The seats still competing: every seat in `order` that has not mucked, undecided seats included."""
        mucked = self.mucked
        return tuple(seat for seat in self.order if seat not in mucked)

    @property
    def is_complete(self) -> bool:
        """Whether no further decision is needed: an `ALL_IN` showdown always, an interactive one once every seat has
        decided or only one contender remains."""
        if self.kind is ShowdownKind.ALL_IN:
            return True
        return len(self.decisions) == len(self.order) or len(self.contenders) == 1

    @property
    def current_decider(self) -> int | None:
        """The seat that must decide next, or None once the showdown is complete."""
        if self.is_complete:
            return None
        return self.order[len(self.decisions)]

    def decide(self, seat: int, action: ShowdownAction) -> Showdown:
        """The record with `action` appended as `seat`'s decision. This record is unchanged.

        Raises `NotShowdownTurnError` when the showdown is complete (an `ALL_IN` showdown always is) or `seat` is not
        the current decider, and then `TypeError` when `action` is not a `ShowdownAction`, so an unsupported action is
        never stored. The turn is checked first, as `apply_action` checks it before legality.
        """
        if self.is_complete:
            raise NotShowdownTurnError("The showdown is complete, so no further decision is accepted")
        if seat != self.current_decider:
            raise NotShowdownTurnError(f"It is not seat {seat}'s turn to decide")
        if not isinstance(action, ShowdownAction):
            raise TypeError(f"A showdown decision must be a ShowdownAction, not {action!r}")
        return replace(self, decisions=(*self.decisions, action))


def canonical_seat_order(seats_from_button: Sequence[int]) -> tuple[int, ...]:
    """The seats clockwise starting with the first seat left of the button, the button last (heads-up, the big blind
    first).

    `seats_from_button` is the hand's seats clockwise with the button first, as in `hand.players`.
    """
    return (*seats_from_button[1:], *seats_from_button[:1])


def decision_order(
    seats_from_button: Sequence[int], live_seats: Collection[int], last_aggressor: int | None
) -> tuple[int, ...]:
    """The live seats in decision order: canonical order (see `canonical_seat_order`), starting with the last aggressor
    and going clockwise when there is one. Without one, the first live seat left of the button decides first.

    Which street or kind of showdown this order applies to is not known here. The last aggressor must be a live seat.
    """
    live = tuple(seat for seat in canonical_seat_order(seats_from_button) if seat in live_seats)
    if last_aggressor is None:
        return live
    start = live.index(last_aggressor)
    return (*live[start:], *live[:start])
