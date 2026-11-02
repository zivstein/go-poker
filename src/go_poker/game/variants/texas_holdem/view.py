"""The Hold'em player view: a read-only snapshot of a table and its current hand for one viewer (ADR 0005).

`holdem_view(table, hand, viewer_seat)` is the single entry point. It is a pure function of the live engine objects and
a viewer, derived on request and never stored. It returns frozen values only: no live engine object and none of the
hand's lists are reachable from a view, and nothing in it can hold the deck, the burned cards or a `player_id`.

Every value is traced as authoritative fact -> visibility rule -> projected value. The viewer rules and the log are in
`game/visibility.py`; the turn, legal actions, pots and strength are the engine's own derived reads, never recomputed
here.
"""

from dataclasses import dataclass
from enum import Enum
from typing import assert_never

from go_poker.core.best_hand import BestHand
from go_poker.core.card import Card
from go_poker.game.betting.legal_actions import LegalActions, legal_actions
from go_poker.game.betting.pots import Pot, pots
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingNotInitializedError
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind, Position
from go_poker.game.showdown import Showdown, ShowdownAction
from go_poker.game.street import Street
from go_poker.game.table import Table
from go_poker.game.variants.texas_holdem.hand_flow import current_actor
from go_poker.game.variants.texas_holdem.hand_strength import hand_strength
from go_poker.game.visibility import (
    LogEvent,
    SettlementView,
    project_log,
    settlement_view,
    viewer_participant_seat,
    visible_hole_card_seats,
)


class TurnKind(Enum):
    """What the seat to act must do: a betting action or a showdown decision."""

    BETTING = "betting"
    SHOWDOWN = "showdown"


class OccupantStatus(Enum):
    """A user-relevant exceptional state of a seated player. A ready player has none (`OccupantView.status` is None)."""

    WAITING_TO_JOIN = "waiting_to_join"
    SITTING_OUT = "sitting_out"


@dataclass(frozen=True)
class OccupantView:
    """The player now sitting at a seat: its stack and its exceptional status, None when ready. There is no
    `player_id`, and the engine's `PlayerStatus` is never exposed."""

    stack: int
    status: OccupantStatus | None


@dataclass(frozen=True)
class SeatView:
    """One table seat, `occupant` None when empty."""

    number: int
    occupant: OccupantView | None


@dataclass(frozen=True)
class ParticipantView:
    """One participant of the hand.

    - `in_front`: the chips in front, committed in the current betting round and not yet collected.
    - `has_live_cards`: cards dealt and neither folded nor mucked; the same for every viewer.
    - `hole_cards`: the cards when visible to the viewer (see `visible_hole_card_seats`), otherwise None: absent, never
      masked.
    - `strength`: the best hand, only for a visible seat that has been dealt; None preflop.
    """

    seat: int
    position: Position
    blind: Blind
    in_front: int
    folded: bool
    all_in: bool
    has_live_cards: bool
    hole_cards: tuple[Card, ...] | None
    strength: BestHand | None


@dataclass(frozen=True)
class Turn:
    """The seat that must act and what it must do; public."""

    seat: int
    kind: TurnKind


@dataclass(frozen=True)
class HandView:
    """The current hand for one viewer.

    - `participants`: in hand order, button first.
    - `legal_actions`: only for the viewer who is the betting actor, else None.
    - `showdown_actions`: `(SHOW, MUCK)` only for the viewer who is the current showdown decider, else None.
    - `showdown`: the showdown record (seats and decisions, never cards).
    - `settlement`: the public result, once settled.
    - `log`: the redacted history, one projected event per event.
    """

    number: int
    stakes: Stakes
    street: Street
    board: tuple[Card, ...]
    participants: tuple[ParticipantView, ...]
    pots: tuple[Pot, ...]
    turn: Turn | None
    legal_actions: LegalActions | None
    showdown_actions: tuple[ShowdownAction, ...] | None
    showdown: Showdown | None
    settlement: SettlementView | None
    log: tuple[LogEvent, ...]


@dataclass(frozen=True)
class HoldemView:
    """Every table seat, and the current hand when there is one."""

    seats: tuple[SeatView, ...]
    hand: HandView | None


def _occupant_status(status: PlayerStatus) -> OccupantStatus | None:
    """Authoritative fact: the player's engine `PlayerStatus`. Rule: only the exceptional states are user-relevant, and
    the match is exhaustive so a new engine status must be classified here. Value: None when ready, else the matching
    `OccupantStatus`."""
    match status:
        case PlayerStatus.READY:
            return None
        case PlayerStatus.WAITING:
            return OccupantStatus.WAITING_TO_JOIN
        case PlayerStatus.SITTING_OUT:
            return OccupantStatus.SITTING_OUT
        case _:
            assert_never(status)


def _seat_views(table: Table) -> tuple[SeatView, ...]:
    """Authoritative fact: each seat's current occupant. Rule: occupancy, stack and the projected status are public.
    Value: a `SeatView` per seat 1..max_seats."""
    views: list[SeatView] = []
    for number in range(1, table.max_seats + 1):
        player = table.get_seat(number).player
        occupant = None if player is None else OccupantView(stack=player.stack, status=_occupant_status(player.status))
        views.append(SeatView(number=number, occupant=occupant))
    return tuple(views)


def _participant_view(hand: PokerHand, state: HandPlayerState, visible_seats: frozenset[int]) -> ParticipantView:
    """Authoritative fact: the participant's state, showdown record and hole cards. Rule: position, blind, chips in
    front, `folded`, `all_in` and `has_live_cards` are public; the cards and the strength follow `visible_seats`."""
    seat = state.seat_number
    dealt = bool(state.hole_cards)
    mucked = hand.showdown is not None and seat in hand.showdown.mucked
    visible = seat in visible_seats
    return ParticipantView(
        seat=seat,
        position=state.position,
        blind=state.blind,
        in_front=state.street_contribution,
        folded=state.folded,
        all_in=state.all_in,
        has_live_cards=dealt and not state.folded and not mucked,
        hole_cards=tuple(state.hole_cards) if visible else None,
        strength=hand_strength(hand, seat) if visible and dealt else None,
    )


def _turn(hand: PokerHand, betting_actor: int | None) -> Turn | None:
    """Authoritative fact: `current_actor`. Rule: public. Value: the seat, and BETTING when it is the betting actor,
    else SHOWDOWN."""
    seat = current_actor(hand)
    if seat is None:
        return None
    return Turn(seat=seat, kind=TurnKind.BETTING if betting_actor == seat else TurnKind.SHOWDOWN)


def _hand_view(hand: PokerHand, participant_seat: int | None) -> HandView:
    betting = hand.betting
    assert betting is not None  # holdem_view rejects an uninitialized hand first
    visible_seats = visible_hole_card_seats(hand, participant_seat)
    turn = _turn(hand, betting.current_actor)
    # Legal actions and the showdown options are private to the one seat that must act, and only for its own turn kind.
    own_kind = turn.kind if turn is not None and turn.seat == participant_seat else None
    return HandView(
        number=hand.number,
        stakes=betting.stakes,
        street=hand.street,
        board=tuple(hand.board),
        participants=tuple(_participant_view(hand, state, visible_seats) for state in hand.players),
        pots=pots(hand),
        turn=turn,
        legal_actions=legal_actions(hand) if own_kind is TurnKind.BETTING else None,
        showdown_actions=tuple(ShowdownAction) if own_kind is TurnKind.SHOWDOWN else None,
        showdown=hand.showdown,
        settlement=None if hand.settlement is None else settlement_view(hand.settlement),
        log=project_log(hand.history, participant_seat),
    )


def holdem_view(table: Table, hand: PokerHand | None, viewer_seat: int | None) -> HoldemView:
    """The Hold'em view of the table and its current hand for a viewer seat; `viewer_seat=None` is the public view.

    The caller passes the table's current hand (not checked). `hand=None` gives the seats only. The viewer has private
    facts only as a participant whose `player_id` is the seat's current occupant's (see `viewer_participant_seat`).

    Raises `InvalidSeatNumber` for a viewer seat outside the table, checked first, and `BettingNotInitializedError`
    for a hand whose betting is not initialized. Both are raised before anything is projected.
    """
    if viewer_seat is not None:
        table.get_seat(viewer_seat)
    if hand is None:
        return HoldemView(seats=_seat_views(table), hand=None)
    if hand.betting is None:
        raise BettingNotInitializedError("Betting has not been initialized for this hand")
    participant_seat = viewer_participant_seat(table, hand, viewer_seat)
    return HoldemView(seats=_seat_views(table), hand=_hand_view(hand, participant_seat))
