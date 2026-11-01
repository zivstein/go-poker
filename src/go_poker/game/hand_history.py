"""The immutable record of one hand (ADR 0004).

A history is a record, not event sourcing: `PokerHand` state is the only input to rules and no rule reads a history.
Every field is an immutable value, and histories are compared by value equality, never by object identity.
"""

from dataclasses import dataclass

from go_poker.game.position import Blind, Position


@dataclass(frozen=True)
class HandParticipant:
    """One seat's participant at the start of a hand: who held the seat, where, and with how many chips."""

    seat: int
    player_id: str
    position: Position
    blind: Blind
    # The stack before any blind is posted.
    starting_stack: int


@dataclass(frozen=True)
class HandStarted:
    """The first event of every history: the hand number and its participants in hand order, button first."""

    number: int
    participants: tuple[HandParticipant, ...]


type HandEvent = HandStarted


@dataclass(frozen=True)
class HandHistory:
    """The append-only sequence of a hand's events; `events[0]` is its `HandStarted`.

    It holds only `events`; the hand number and participants are read from `HandStarted`. Like `Showdown`, it does not
    validate on construction: engine-produced histories are well-formed. A history never changes once taken; recording
    replaces it with a new value that has one more event.
    """

    events: tuple[HandEvent, ...]

    @property
    def number(self) -> int:
        return self.events[0].number

    @property
    def participants(self) -> tuple[HandParticipant, ...]:
        return self.events[0].participants


def _appended(history: HandHistory, event: HandEvent) -> HandHistory:
    """Return a new history with the event added. Engine-internal: the recording primitive of the hand operations."""
    return HandHistory((*history.events, event))
