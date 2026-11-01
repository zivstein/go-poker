"""The immutable record of one hand (ADR 0004).

A history is a record, not event sourcing: `PokerHand` state is the only input to rules and no rule reads a history.
Every field is an immutable value, and histories are compared by value equality, never by object identity.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING

from go_poker.core.card import Card
from go_poker.game.betting.actions import Action
from go_poker.game.betting.stakes import Stakes
from go_poker.game.position import Blind, Position
from go_poker.game.showdown import ShowdownAction, ShowdownKind
from go_poker.game.street import Street

if TYPE_CHECKING:
    # Type-only: settlement reaches PokerHand, which owns the history, through the pots it derives from a hand.
    from go_poker.game.settlement import Settlement


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


@dataclass(frozen=True)
class BlindPost:
    """One posted blind: the seat, which blind, the chips actually posted (the whole stack for a short blind), and
    whether the seat was all-in right after posting."""

    seat: int
    blind: Blind
    chips: int
    all_in: bool


@dataclass(frozen=True)
class BlindsPosted:
    """The blinds of the hand: its stakes and the posts in posting order, small blind then big blind."""

    stakes: Stakes
    posts: tuple[BlindPost, ...]


@dataclass(frozen=True)
class SeatHoleCards:
    """One seat's hole cards, in the order the seat received them."""

    seat: int
    cards: tuple[Card, ...]


@dataclass(frozen=True)
class HoleCardsDealt:
    """The hole cards dealt to every participant, in hand order, button first."""

    hole_cards: tuple[SeatHoleCards, ...]


@dataclass(frozen=True)
class StreetDealt:
    """A street dealt: the cards burned and the board cards dealt by this deal alone, in draw order."""

    street: Street
    burned: tuple[Card, ...]
    cards: tuple[Card, ...]


@dataclass(frozen=True)
class BettingRoundStarted:
    """A betting round started on a street after the preflop; the preflop round starts with `BlindsPosted`."""

    street: Street


@dataclass(frozen=True)
class ActionTaken:
    """A betting action as requested (a bet or raise keeps its target), the chips it actually committed (0 for a fold
    or check), and whether the seat was all-in right after committing them."""

    seat: int
    action: Action
    chips: int
    all_in: bool


@dataclass(frozen=True)
class ChipsReturned:
    """The uncalled chips returned to a seat's stack when a betting round was collected."""

    seat: int
    chips: int


@dataclass(frozen=True)
class BettingRoundCompleted:
    """A betting round on this street completed; any chips in front were collected."""

    street: Street


@dataclass(frozen=True)
class ShowdownStarted:
    """A showdown started: its kind and its order, which is `hand.showdown.order` at the start. For `INTERACTIVE` it is
    the decision order; for `ALL_IN` it is every live seat in canonical storage order, not a sequence of actions."""

    kind: ShowdownKind
    order: tuple[int, ...]


@dataclass(frozen=True)
class ShowdownDecided:
    """One seat's SHOW or MUCK decision in an `INTERACTIVE` showdown."""

    seat: int
    action: ShowdownAction


@dataclass(frozen=True)
class HandSettled:
    """The last event of every completed history: the hand's settlement, equal to `hand.settlement`."""

    settlement: Settlement


type HandEvent = (
    HandStarted
    | BlindsPosted
    | HoleCardsDealt
    | StreetDealt
    | BettingRoundStarted
    | ActionTaken
    | ChipsReturned
    | BettingRoundCompleted
    | ShowdownStarted
    | ShowdownDecided
    | HandSettled
)


@dataclass(frozen=True)
class HandHistory:
    """The append-only sequence of a hand's events; `events[0]` is its `HandStarted`.

    It holds only `events`; the hand number and participants are read from `HandStarted`. Like `Showdown`, it does not
    validate on construction: engine-produced histories are well-formed. A history never changes once taken; recording
    replaces it with a new value that has one more event. A history is complete once it ends with `HandSettled`; a
    history taken earlier stays incomplete, and a completed one is the durable record of the hand.
    """

    events: tuple[HandEvent, ...]

    @property
    def _started(self) -> HandStarted:
        first = self.events[0]
        if not isinstance(first, HandStarted):
            raise TypeError("A hand history starts with HandStarted")
        return first

    @property
    def number(self) -> int:
        return self._started.number

    @property
    def participants(self) -> tuple[HandParticipant, ...]:
        return self._started.participants

    @property
    def is_complete(self) -> bool:
        """Whether the hand is settled: the history ends with `HandSettled`."""
        return isinstance(self.events[-1], HandSettled)

    @property
    def settlement(self) -> Settlement | None:
        """The hand's settlement from `HandSettled`, or None while the history is incomplete."""
        last = self.events[-1]
        return last.settlement if isinstance(last, HandSettled) else None


def _appended(history: HandHistory, event: HandEvent) -> HandHistory:
    """Return a new history with the event added. Engine-internal: the recording primitive of the hand operations."""
    return HandHistory((*history.events, event))
