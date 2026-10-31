from collections.abc import Collection, Sequence
from dataclasses import dataclass
from enum import Enum


class RevealKind(Enum):
    """How a hand's live players were revealed: all at once because of an all-in, or in the river show order."""

    ALL_IN = "all_in"
    SHOWDOWN = "showdown"


@dataclass(frozen=True)
class Reveal:
    """The immutable record that a hand's live players have been revealed, and which seats were.

    It records seats, not cards. For `RevealKind.ALL_IN` every live hand is tabled at once, so `seats` are in canonical
    seat order (see `canonical_seat_order`), which is storage order only and not a reveal sequence. For
    `RevealKind.SHOWDOWN` `seats` is the sequential river show order (see `show_order`). Folded seats never appear.
    """

    kind: RevealKind
    seats: tuple[int, ...]


def canonical_seat_order(seats_from_button: Sequence[int]) -> tuple[int, ...]:
    """The seats clockwise starting with the first seat left of the button, the button last (heads-up, the big blind
    first).

    `seats_from_button` is the hand's seats clockwise with the button first, as in `hand.players`.
    """
    return (*seats_from_button[1:], *seats_from_button[:1])


def show_order(
    seats_from_button: Sequence[int], live_seats: Collection[int], last_aggressor: int | None
) -> tuple[int, ...]:
    """The live seats in show order: canonical order (see `canonical_seat_order`), starting with the last aggressor and
    going clockwise when there is one. Without one, the first live seat left of the button shows first.

    Which street or kind of showdown this order applies to is not known here. The last aggressor must be a live seat.
    """
    live = tuple(seat for seat in canonical_seat_order(seats_from_button) if seat in live_seats)
    if last_aggressor is None:
        return live
    start = live.index(last_aggressor)
    return (*live[start:], *live[:start])
