"""Who may see what of a hand, and the redacted hand log (ADR 0005 §2-5, ADR 0004 §9).

Everything here is a read-only projection: a pure function of the table, the hand and a viewer, derived on request and
never stored. No rule reads it and it changes nothing. It is variant-agnostic; the Hold'em view that uses it is in
`game/variants/texas_holdem/view.py`.

Two parts:

- the viewer rules: `viewer_participant_seat` (which seat's private facts a viewer has) and `visible_hole_card_seats`
  (whose hole cards that viewer sees);
- the log projection: `project_log` and `project_event` turn the authoritative `HandHistory` into projection-owned
  values, and `settlement_view` does the same for a `Settlement`. The log is redacted by allowlist: every event is
  rebuilt field by field from named source fields, so a field added to an event reaches a view only when a case here
  copies it, and a new event type fails the type checker until it is classified.

The projected values never hold a `HandEvent`, a `Settlement`, a `player_id`, the burned cards or another seat's
hole cards. They reuse only safe leaf values (`Card`, the enums, `Action`, `Stakes`, `Pot`, `HandRank`).
"""

from dataclasses import dataclass
from typing import assert_never

from go_poker.core.card import Card
from go_poker.core.hand_rank import HandRank
from go_poker.game.betting.actions import Action
from go_poker.game.betting.pots import Pot
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_history import (
    ActionTaken,
    BettingRoundCompleted,
    BettingRoundStarted,
    BlindsPosted,
    ChipsReturned,
    HandEvent,
    HandHistory,
    HandSettled,
    HandStarted,
    HoleCardsDealt,
    ShowdownDecided,
    ShowdownStarted,
    StreetDealt,
)
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind, Position
from go_poker.game.settlement import Settlement
from go_poker.game.showdown import ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.table import Table

# --- Viewer rules ---


def viewer_participant_seat(table: Table, hand: PokerHand, viewer_seat: int | None) -> int | None:
    """The seat whose private facts a viewer has, or None for the public facts only.

    Authoritative fact: the hand's participant at the viewer seat and the table's current occupant of that seat.
    Rule: a viewer has private facts only when both exist and carry the same `player_id`; ids are compared, never
    objects. An empty seat, a seated non-participant, a new occupant of a settled hand's seat and `viewer_seat=None`
    all get None. A seat outside the table raises `InvalidSeatNumber` (through `table.get_seat`).
    """
    if viewer_seat is None:
        return None
    occupant = table.get_seat(viewer_seat).player
    if occupant is None:
        return None
    participant = next((state for state in hand.players if state.seat_number == viewer_seat), None)
    if participant is None or participant.player.player_id != occupant.player_id:
        return None
    return viewer_seat


def visible_hole_card_seats(hand: PokerHand, participant_seat: int | None) -> frozenset[int]:
    """The seats whose hole cards the viewer sees: the viewer's own participant seat plus the shown seats.

    Authoritative fact: `hand.showdown.shown`, the single source of shown cards (every live seat of an `ALL_IN`
    showdown, each SHOW of an `INTERACTIVE` one). Rule: own cards are always visible, including after a fold or a
    muck; a shown seat is visible to everyone; every other seat (folded, mucked, unshown) is hidden. Strength follows
    the same set.
    """
    shown = frozenset(hand.showdown.shown) if hand.showdown is not None else frozenset()
    if participant_seat is None:
        return shown
    return shown | {participant_seat}


# --- Projected log values ---


@dataclass(frozen=True)
class HandParticipantView:
    """A hand participant at the start of the hand. Unlike `HandParticipant` it has no `player_id`."""

    seat: int
    position: Position
    blind: Blind
    starting_stack: int


@dataclass(frozen=True)
class BlindPostView:
    """A posted blind; all of its facts are public."""

    seat: int
    blind: Blind
    chips: int
    all_in: bool


@dataclass(frozen=True)
class PotAwardView:
    """One pot and the (seat, chips) shares it paid; public."""

    pot: Pot
    shares: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class SettlementView:
    """The public result of a hand: the pot awards and the showdown ranks of the shown seats only.

    Authoritative fact: `Settlement`, whose `showdown_ranks` hold exactly the shown seats, so no unshown seat's rank is
    in it.
    """

    pot_awards: tuple[PotAwardView, ...]
    showdown_ranks: tuple[tuple[int, HandRank], ...]


@dataclass(frozen=True)
class HandStartedView:
    number: int
    participants: tuple[HandParticipantView, ...]


@dataclass(frozen=True)
class BlindsPostedView:
    stakes: Stakes
    posts: tuple[BlindPostView, ...]


@dataclass(frozen=True)
class HoleCardsDealtView:
    """That hole cards were dealt, with only the viewer's own cards: `own_cards` is None for a viewer who is not a
    participant, and no other seat's cards are ever copied."""

    own_cards: tuple[Card, ...] | None


@dataclass(frozen=True)
class StreetDealtView:
    """A street dealt: its board cards only. The burned cards are not projected."""

    street: Street
    cards: tuple[Card, ...]


@dataclass(frozen=True)
class BettingRoundStartedView:
    street: Street


@dataclass(frozen=True)
class ActionTakenView:
    seat: int
    action: Action
    chips: int
    all_in: bool


@dataclass(frozen=True)
class ChipsReturnedView:
    seat: int
    chips: int


@dataclass(frozen=True)
class BettingRoundCompletedView:
    street: Street


@dataclass(frozen=True)
class ShowdownStartedView:
    kind: ShowdownKind
    order: tuple[int, ...]


@dataclass(frozen=True)
class ShowdownDecidedView:
    seat: int
    action: ShowdownAction


@dataclass(frozen=True)
class HandSettledView:
    settlement: SettlementView


type LogEvent = (
    HandStartedView
    | BlindsPostedView
    | HoleCardsDealtView
    | StreetDealtView
    | BettingRoundStartedView
    | ActionTakenView
    | ChipsReturnedView
    | BettingRoundCompletedView
    | ShowdownStartedView
    | ShowdownDecidedView
    | HandSettledView
)


# --- Log projection ---


def settlement_view(settlement: Settlement) -> SettlementView:
    """The public form of a settlement, shared by the hand view and the log's `HandSettledView`.

    Authoritative fact: the pot awards and `showdown_ranks` (shown seats only). Rule: both are public. Projected value:
    a `SettlementView` of fresh tuples and `PotAwardView`s, holding no `Settlement`.
    """
    return SettlementView(
        pot_awards=tuple(PotAwardView(pot=award.pot, shares=tuple(award.shares)) for award in settlement.pot_awards),
        showdown_ranks=tuple(settlement.showdown_ranks),
    )


def project_event(event: HandEvent, participant_seat: int | None) -> LogEvent:
    """Project one authoritative event for a viewer, field by field.

    Authoritative fact: the event. Rule (ADR 0004 §9): every fact is public except the hole cards, of which the viewer
    keeps only its own, and the burned cards, which are dropped; `player_id` is dropped from the participants.
    Projected value: the matching `*View`. The match is exhaustive, so a new event type fails the type checker until
    it is classified here.
    """
    match event:
        case HandStarted(number=number, participants=participants):
            return HandStartedView(
                number=number,
                participants=tuple(
                    HandParticipantView(
                        seat=participant.seat,
                        position=participant.position,
                        blind=participant.blind,
                        starting_stack=participant.starting_stack,
                    )
                    for participant in participants
                ),
            )
        case BlindsPosted(stakes=stakes, posts=posts):
            return BlindsPostedView(
                stakes=stakes,
                posts=tuple(
                    BlindPostView(seat=post.seat, blind=post.blind, chips=post.chips, all_in=post.all_in)
                    for post in posts
                ),
            )
        case HoleCardsDealt(hole_cards=hole_cards):
            own = next((dealt.cards for dealt in hole_cards if dealt.seat == participant_seat), None)
            return HoleCardsDealtView(own_cards=None if own is None else tuple(own))
        case StreetDealt(street=street, cards=cards):
            return StreetDealtView(street=street, cards=tuple(cards))
        case BettingRoundStarted(street=street):
            return BettingRoundStartedView(street=street)
        case ActionTaken(seat=seat, action=action, chips=chips, all_in=all_in):
            return ActionTakenView(seat=seat, action=action, chips=chips, all_in=all_in)
        case ChipsReturned(seat=seat, chips=chips):
            return ChipsReturnedView(seat=seat, chips=chips)
        case BettingRoundCompleted(street=street):
            return BettingRoundCompletedView(street=street)
        case ShowdownStarted(kind=kind, order=order):
            return ShowdownStartedView(kind=kind, order=tuple(order))
        case ShowdownDecided(seat=seat, action=action):
            return ShowdownDecidedView(seat=seat, action=action)
        case HandSettled(settlement=settlement):
            return HandSettledView(settlement=settlement_view(settlement))
        case _:
            assert_never(event)


def project_log(history: HandHistory, participant_seat: int | None) -> tuple[LogEvent, ...]:
    """The hand's log for a viewer: one projected event per authoritative event, in order, none omitted.

    Shown cards are never added to the log; they appear only in the participants' hole cards.
    """
    return tuple(project_event(event, participant_seat) for event in history.events)
