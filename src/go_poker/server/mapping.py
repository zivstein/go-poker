"""Views and command results to wire models, mapped field by field (ADR 0008 §2, ADR 0009 §3, §10-§12).

Two rules hold everywhere here:

1. **Explicit mapping only.** Every wire field is named by a function in this module. There is no `model_validate` of a
   view, no `from_attributes`, no `asdict`, no `__dict__` and no other bulk copy, so a field added to a view or to a
   log event reaches the wire only when a mapper here copies it. `tests/server/test_mapping_is_an_allowlist.py` guards
   that on the source text.
2. **Explicit tables.** Every engine enum becomes a wire string through a table below, each exhaustive over its enum
   and checked by `tests/server/test_mapping_tables.py`. No wire string is ever derived from an enum's `.value` or
   `.name`: the protocol's strings are its own (ADR 0009 §3).

Two engine values are deliberately dropped, because the wire has no field for them: `HandView.stakes` (the view's
`settings` carries the blinds) and `BlindsPostedView.stakes`. `HandRank.tiebreakers` is dropped too: only the category
is public (ADR 0009 §10).
"""

from collections.abc import Iterable, Mapping
from typing import assert_never

from go_poker.app.pre_actions import PreAction, PreActionKind
from go_poker.app.results import Accepted, Rejected, RejectionCode, TransitionCause
from go_poker.app.views import SessionSeatView, TablePhase, TableSettings, TableView, YouView
from go_poker.core.best_hand import BestHand
from go_poker.core.card import Card, Rank, Suit
from go_poker.core.hand_rank import HandCategory
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.legal_actions import LegalActions
from go_poker.game.betting.pots import Pot
from go_poker.game.position import Blind, Position
from go_poker.game.showdown import Showdown, ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import HOLE_CARD_COUNT
from go_poker.game.variants.texas_holdem.view import (
    HandView,
    OccupantStatus,
    ParticipantView,
    SeatView,
    Turn,
    TurnKind,
)
from go_poker.game.visibility import (
    ActionTakenView,
    BettingRoundCompletedView,
    BettingRoundStartedView,
    BlindsPostedView,
    ChipsReturnedView,
    HandSettledView,
    HandStartedView,
    HoleCardsDealtView,
    LogEvent,
    SettlementView,
    ShowdownDecidedView,
    ShowdownStartedView,
    StreetDealtView,
)
from go_poker.server import dto

# --- Tables: engine value -> wire string (ADR 0009 §3, §12) ---

RANKS: Mapping[Rank, str] = {
    Rank.TWO: "2",
    Rank.THREE: "3",
    Rank.FOUR: "4",
    Rank.FIVE: "5",
    Rank.SIX: "6",
    Rank.SEVEN: "7",
    Rank.EIGHT: "8",
    Rank.NINE: "9",
    Rank.TEN: "T",
    Rank.JACK: "J",
    Rank.QUEEN: "Q",
    Rank.KING: "K",
    Rank.ACE: "A",
}

SUITS: Mapping[Suit, str] = {Suit.CLUBS: "c", Suit.DIAMONDS: "d", Suit.HEARTS: "h", Suit.SPADES: "s"}

PHASES: Mapping[TablePhase, dto.Phase] = {
    TablePhase.NOT_STARTED: "not_started",
    TablePhase.HAND_IN_PROGRESS: "hand_in_progress",
    TablePhase.HAND_COMPLETE: "hand_complete",
    TablePhase.WAITING_FOR_PLAYERS: "waiting_for_players",
}

STREETS: Mapping[Street, dto.Street] = {
    Street.PREFLOP: "preflop",
    Street.FLOP: "flop",
    Street.TURN: "turn",
    Street.RIVER: "river",
}

POSITIONS: Mapping[Position, dto.Position] = {
    Position.BTN: "btn",
    Position.SB: "sb",
    Position.BB: "bb",
    Position.UTG: "utg",
    Position.UTG1: "utg1",
    Position.MP: "mp",
    Position.LJ: "lj",
    Position.HJ: "hj",
    Position.CO: "co",
}

# `Blind.NONE` is "no blind", which the wire states as null.
BLINDS: Mapping[Blind, dto.Blind | None] = {Blind.NONE: None, Blind.SMALL: "small", Blind.BIG: "big"}

# A ready occupant has no status, which the wire states as null (the engine view already uses None for it).
OCCUPANT_STATUSES: Mapping[OccupantStatus | None, dto.OccupantStatus | None] = {
    None: None,
    OccupantStatus.WAITING_TO_JOIN: "waiting_to_join",
    OccupantStatus.SITTING_OUT: "sitting_out",
}

TURN_KINDS: Mapping[TurnKind, dto.TurnKind] = {TurnKind.BETTING: "betting", TurnKind.SHOWDOWN: "showdown"}

SHOWDOWN_KINDS: Mapping[ShowdownKind, dto.ShowdownKind] = {
    ShowdownKind.ALL_IN: "all_in",
    ShowdownKind.INTERACTIVE: "interactive",
}

SHOWDOWN_DECISIONS: Mapping[ShowdownAction, dto.ShowdownDecision] = {
    ShowdownAction.SHOW: "show",
    ShowdownAction.MUCK: "muck",
}

HAND_CATEGORIES: Mapping[HandCategory, dto.HandCategory] = {
    HandCategory.HIGH_CARD: "high_card",
    HandCategory.ONE_PAIR: "one_pair",
    HandCategory.TWO_PAIR: "two_pair",
    HandCategory.THREE_OF_A_KIND: "three_of_a_kind",
    HandCategory.STRAIGHT: "straight",
    HandCategory.FLUSH: "flush",
    HandCategory.FULL_HOUSE: "full_house",
    HandCategory.FOUR_OF_A_KIND: "four_of_a_kind",
    HandCategory.STRAIGHT_FLUSH: "straight_flush",
}

PRE_ACTION_KINDS: Mapping[PreActionKind, dto.PreActionKind] = {
    PreActionKind.CHECK: "check",
    PreActionKind.CHECK_OR_FOLD: "check_or_fold",
    PreActionKind.FOLD: "fold",
    PreActionKind.CALL_CURRENT: "call_current",
}

ACTIONS: Mapping[ActionType, dto.Action] = {
    ActionType.FOLD: "fold",
    ActionType.CHECK: "check",
    ActionType.CALL: "call",
    ActionType.BET: "bet",
    ActionType.RAISE: "raise",
}

# The rejection codes a `rejected` message carries (ADR 0009 §12). None marks a code that never reaches the wire this
# way: the five that only an HTTP join produces, and `NOT_AT_HAND_BOUNDARY`, which is internal to `advance_hand`.
REJECTED_CODES: Mapping[RejectionCode, dto.RejectedCode | None] = {
    RejectionCode.STALE_REVISION: "STALE_REVISION",
    RejectionCode.NOT_A_MEMBER: "NOT_A_MEMBER",
    RejectionCode.ALREADY_MEMBER: None,
    RejectionCode.LEFT_TABLE: None,
    RejectionCode.DISPLAY_NAME_TAKEN: None,
    RejectionCode.SEAT_TAKEN: None,
    RejectionCode.INVALID_SEAT: None,
    RejectionCode.NOT_HOST: "NOT_HOST",
    RejectionCode.GAME_ALREADY_STARTED: "GAME_ALREADY_STARTED",
    RejectionCode.NOT_ENOUGH_PLAYERS: "NOT_ENOUGH_PLAYERS",
    RejectionCode.NO_HAND_IN_PROGRESS: "NO_HAND_IN_PROGRESS",
    RejectionCode.NOT_YOUR_TURN: "NOT_YOUR_TURN",
    RejectionCode.ILLEGAL_ACTION: "ILLEGAL_ACTION",
    RejectionCode.LEAVE_PENDING: "LEAVE_PENDING",
    RejectionCode.NO_CHANGE: "NO_CHANGE",
    RejectionCode.NOT_AT_HAND_BOUNDARY: None,
    RejectionCode.PRE_ACTION_UNAVAILABLE: "PRE_ACTION_UNAVAILABLE",
}

TRANSITION_CAUSES: Mapping[TransitionCause, dto.SnapshotCause] = {
    TransitionCause.COMMAND: "command",
    TransitionCause.LEAVE_AUTO_ACTION: "leave_auto_action",
    TransitionCause.PRE_ACTION: "pre_action",
    TransitionCause.HAND_BOUNDARY: "hand_boundary",
    TransitionCause.RESUME: "resume",
}

# The two causes that are the server's own, not a shared transition's (ADR 0009 §9).
CONNECTED: dto.SnapshotCause = "connected"
PRIVATE: dto.SnapshotCause = "private"

# --- Tables: wire string -> engine value (the inbound direction, ADR 0009 §6) ---
#
# These are the exact inverses of the outbound tables above, written out rather than derived, so that each direction
# is readable on its own and a test compares them.

WIRE_ACTIONS: Mapping[dto.Action, ActionType] = {
    "fold": ActionType.FOLD,
    "check": ActionType.CHECK,
    "call": ActionType.CALL,
    "bet": ActionType.BET,
    "raise": ActionType.RAISE,
}

WIRE_SHOWDOWN_DECISIONS: Mapping[dto.ShowdownDecision, ShowdownAction] = {
    "show": ShowdownAction.SHOW,
    "muck": ShowdownAction.MUCK,
}

WIRE_PRE_ACTION_KINDS: Mapping[dto.PreActionKind, PreActionKind] = {
    "check": PreActionKind.CHECK,
    "check_or_fold": PreActionKind.CHECK_OR_FOLD,
    "fold": PreActionKind.FOLD,
    "call_current": PreActionKind.CALL_CURRENT,
}


# --- Leaf values ---


def card(value: Card) -> dto.Card:
    """A card as two characters, rank then suit (ADR 0009 §3)."""
    return f"{RANKS[value.rank]}{SUITS[value.suit]}"


def cards(values: Iterable[Card]) -> list[dto.Card]:
    """Cards in the order given; the order is part of the contract everywhere a card list appears."""
    return [card(value) for value in values]


def ascending_seats(seats: Iterable[int]) -> list[int]:
    """The seats of an engine `frozenset` as the ascending list the wire defines (ADR 0009 §10)."""
    return sorted(seats)


def blind(value: Blind) -> dto.Blind | None:
    return BLINDS[value]


def posted_blind(value: Blind) -> dto.Blind:
    """The blind of a posted blind, which is always a real blind."""
    posted = BLINDS[value]
    if posted is None:
        raise ValueError("A posted blind cannot be Blind.NONE")
    return posted


def rejected_code(code: RejectionCode) -> dto.RejectedCode:
    """The wire code of a domain rejection that a command on the WebSocket produced."""
    wire = REJECTED_CODES[code]
    if wire is None:
        raise ValueError(f"{code.name} never reaches the wire in a rejected message (ADR 0009 §12)")
    return wire


def snapshot_cause(cause: TransitionCause) -> dto.SnapshotCause:
    """The wire cause of a shared transition's snapshot."""
    return TRANSITION_CAUSES[cause]


# --- The view (ADR 0009 §10, §11) ---


def settings(table_settings: TableSettings) -> dto.Settings:
    """The table's settings. `variant` and `betting_structure` are v1 constants: the only engine game is No-Limit
    Hold'em, and the fields exist for display and client configuration (ADR 0009 §10)."""
    return dto.Settings(
        variant="texas_holdem",
        betting_structure="no_limit",
        small_blind=table_settings.stakes.small_blind,
        big_blind=table_settings.stakes.big_blind,
        buy_in=table_settings.buy_in,
        max_seats=table_settings.max_seats,
    )


def seat(session_seat: SessionSeatView, game_seat: SeatView) -> dto.Seat:
    """One wire seat, joined from the two views of that seat number: the display name and the host flag come from the
    session's seat, the stack and the status from the engine's occupant. Both must agree on whether the seat is
    taken."""
    assert session_seat.number == game_seat.number, "the two views of a seat must be of the same seat number"
    display_name = session_seat.display_name
    occupant = game_seat.occupant
    assert (display_name is None) == (occupant is None), "the session and the engine disagree on seat occupancy"
    if display_name is None or occupant is None:
        return dto.Seat(seat=session_seat.number, occupant=None)
    return dto.Seat(
        seat=session_seat.number,
        occupant=dto.Occupant(
            display_name=display_name.value,
            is_host=session_seat.is_host,
            stack=occupant.stack,
            status=OCCUPANT_STATUSES[occupant.status],
        ),
    )


def seats(view: TableView) -> list[dto.Seat]:
    """Every seat from 1 to `max_seats`, ascending, each joined from the session's and the engine's seat views."""
    by_number = {game_seat.number: game_seat for game_seat in view.game.seats}
    assert len(by_number) == len(view.game.seats), "the engine's seat views must have distinct numbers"
    return [seat(session_seat, by_number[session_seat.number]) for session_seat in view.seats]


def strength(best_hand: BestHand) -> dto.Strength:
    """The viewer-visible hand strength: the category, the engine's English description, and the five cards in order of
    significance. The rank's tiebreakers never reach the wire."""
    return dto.Strength(
        category=HAND_CATEGORIES[best_hand.rank.category],
        description=best_hand.description,
        cards=cards(best_hand.cards),
    )


def hidden_card_count(participant_view: ParticipantView) -> int:
    """How many card backs to draw: none when the viewer sees the cards or the seat has no live cards, otherwise the
    engine's `HOLE_CARD_COUNT`, its single source (ADR 0009 §10)."""
    if participant_view.hole_cards is not None or not participant_view.has_live_cards:
        return 0
    return HOLE_CARD_COUNT


def participant(participant_view: ParticipantView) -> dto.Participant:
    return dto.Participant(
        seat=participant_view.seat,
        position=POSITIONS[participant_view.position],
        blind=blind(participant_view.blind),
        in_front=participant_view.in_front,
        folded=participant_view.folded,
        all_in=participant_view.all_in,
        has_live_cards=participant_view.has_live_cards,
        hole_cards=None if participant_view.hole_cards is None else cards(participant_view.hole_cards),
        hidden_card_count=hidden_card_count(participant_view),
        strength=None if participant_view.strength is None else strength(participant_view.strength),
    )


def pot(value: Pot) -> dto.Pot:
    """One pot layer, exactly as the engine derived it: the server never merges or re-splits pots (ADR 0009 §10)."""
    return dto.Pot(amount=value.amount, eligible_seats=ascending_seats(value.eligible_seats))


def turn(value: Turn) -> dto.Turn:
    return dto.Turn(seat=value.seat, kind=TURN_KINDS[value.kind])


def legal_actions(value: LegalActions) -> dto.LegalActions:
    """The actor's legal actions, field by field with the engine's meanings (ADR 0009 §11)."""
    return dto.LegalActions(
        can_fold=value.can_fold,
        can_check=value.can_check,
        can_call=value.can_call,
        amount_owed=value.amount_owed,
        call_amount=value.call_amount,
        call_is_all_in=value.call_is_all_in,
        can_bet=value.can_bet,
        can_raise=value.can_raise,
        min_full_target=value.min_full_target,
        max_target=value.max_target,
        short_all_in_target=value.short_all_in_target,
    )


def showdown(record: Showdown) -> dto.Showdown:
    """The showdown record. `decisions` pairs each decision with the seat that made it: the engine's `order` holds
    every seat that reaches the showdown, so it can be longer than `decisions`."""
    return dto.Showdown(
        kind=SHOWDOWN_KINDS[record.kind],
        order=list(record.order),
        decisions=[
            dto.SeatDecision(seat=decider, decision=SHOWDOWN_DECISIONS[action])
            for decider, action in zip(record.order, record.decisions, strict=False)
        ],
    )


def settlement(view: SettlementView) -> dto.Settlement:
    """The hand's result: each pot's award with its shares in the engine's odd-chip order, and the shown seats' hand
    categories in hand order."""
    return dto.Settlement(
        pot_awards=[
            dto.PotAward(
                amount=award.pot.amount,
                eligible_seats=ascending_seats(award.pot.eligible_seats),
                shares=[dto.Share(seat=share_seat, amount=amount) for share_seat, amount in award.shares],
            )
            for award in view.pot_awards
        ],
        shown_ranks=[
            dto.ShownRank(seat=shown_seat, category=HAND_CATEGORIES[rank.category])
            for shown_seat, rank in view.showdown_ranks
        ],
    )


def pre_action(intent: PreAction) -> dto.PreAction:
    return dto.PreAction(kind=PRE_ACTION_KINDS[intent.kind], amount=intent.amount)


def you(view: YouView) -> dto.You:
    """The viewer's own seat and private intents (ADR 0006 §4)."""
    return dto.You(
        seat=view.seat,
        is_host=view.is_host,
        pending_leave=view.pending_leave,
        pending_sit_out=view.pending_sit_out,
        pre_action=None if view.pre_action is None else pre_action(view.pre_action),
        pre_action_options=[pre_action(option) for option in view.pre_action_options],
    )


def hand(view: HandView) -> dto.Hand:
    """The current hand for one viewer. `view.stakes` is not mapped: the wire carries the blinds in `settings`."""
    return dto.Hand(
        number=view.number,
        street=STREETS[view.street],
        board=cards(view.board),
        participants=[participant(each) for each in view.participants],
        pots=[pot(each) for each in view.pots],
        turn=None if view.turn is None else turn(view.turn),
        legal_actions=None if view.legal_actions is None else legal_actions(view.legal_actions),
        showdown_actions=(
            None if view.showdown_actions is None else [SHOWDOWN_DECISIONS[action] for action in view.showdown_actions]
        ),
        showdown=None if view.showdown is None else showdown(view.showdown),
        settlement=None if view.settlement is None else settlement(view.settlement),
        log=[log_event(event) for event in view.log],
    )


def table_view(view: TableView) -> dto.View:
    """One member's whole view. `view.revision` is not mapped: the revision is a field of the snapshot that carries
    this view (ADR 0009 §7)."""
    return dto.View(
        table_id=view.table_id,
        join_code=view.code,
        settings=settings(view.settings),
        phase=PHASES[view.phase],
        seats=seats(view),
        hand=None if view.game.hand is None else hand(view.game.hand),
        you=you(view.you),
    )


# --- The log (ADR 0009 §10) ---


def log_event(event: LogEvent) -> dto.LogEvent:
    """One projected log event. The match is exhaustive, so a new projected event type fails the type checker until it
    is classified here. `BlindsPostedView.stakes` is dropped: the wire's `blinds_posted` has no stakes."""
    match event:
        case HandStartedView(number=number, participants=participants):
            return dto.HandStartedEvent(
                event="hand_started",
                number=number,
                participants=[
                    dto.LogParticipant(
                        seat=each.seat,
                        position=POSITIONS[each.position],
                        blind=blind(each.blind),
                        starting_stack=each.starting_stack,
                    )
                    for each in participants
                ],
            )
        case BlindsPostedView(posts=posts):
            return dto.BlindsPostedEvent(
                event="blinds_posted",
                posts=[
                    dto.BlindPost(seat=post.seat, blind=posted_blind(post.blind), chips=post.chips, all_in=post.all_in)
                    for post in posts
                ],
            )
        case HoleCardsDealtView(own_cards=own_cards):
            return dto.HoleCardsDealtEvent(
                event="hole_cards_dealt", own_cards=None if own_cards is None else cards(own_cards)
            )
        case StreetDealtView(street=street, cards=board_cards):
            return dto.StreetDealtEvent(event="street_dealt", street=STREETS[street], cards=cards(board_cards))
        case BettingRoundStartedView(street=street):
            return dto.BettingRoundStartedEvent(event="betting_round_started", street=STREETS[street])
        case ActionTakenView(seat=action_seat, action=action, chips=chips, all_in=all_in):
            return dto.ActionTakenEvent(
                event="action_taken",
                seat=action_seat,
                action=ACTIONS[action.type],
                target=action.amount,
                chips=chips,
                all_in=all_in,
            )
        case ChipsReturnedView(seat=returned_seat, chips=chips):
            return dto.ChipsReturnedEvent(event="chips_returned", seat=returned_seat, chips=chips)
        case BettingRoundCompletedView(street=street):
            return dto.BettingRoundCompletedEvent(event="betting_round_completed", street=STREETS[street])
        case ShowdownStartedView(kind=kind, order=order):
            return dto.ShowdownStartedEvent(event="showdown_started", kind=SHOWDOWN_KINDS[kind], order=list(order))
        case ShowdownDecidedView(seat=decider, action=decision):
            return dto.ShowdownDecidedEvent(
                event="showdown_decided", seat=decider, decision=SHOWDOWN_DECISIONS[decision]
            )
        case HandSettledView(settlement=settled):
            return dto.HandSettledEvent(event="hand_settled", settlement=settlement(settled))
        case _:
            assert_never(event)


# --- Messages (ADR 0009 §7, §8) ---


def snapshot(revision: int, cause: dto.SnapshotCause, view: TableView) -> dto.Snapshot:
    """One member's snapshot, built from the view captured at that revision. The caller passes the revision and the
    cause, because `connected` and `private` snapshots are not transitions (ADR 0009 §9)."""
    assert revision == view.revision, "a snapshot must carry the revision of the view it was captured at"
    return dto.Snapshot(type="snapshot", revision=revision, cause=cause, view=table_view(view))


def accepted(request_id: str, result: Accepted) -> dto.Accepted:
    """The outcome of an applied command: its `request_id` and the table's revision after it, which is the last shared
    transition's revision, or the unchanged revision of the requester's view for a private command."""
    if result.transitions:
        revision = result.transitions[-1].revision
    else:
        assert result.view is not None, "a private command's result always carries the requester's view"
        revision = result.view.revision
    return dto.Accepted(type="accepted", request_id=request_id, revision=revision)


def rejected(request_id: str, result: Rejected) -> dto.Rejected:
    """The outcome of a domain rejection. The message is the application's own English diagnostic, passed through
    verbatim: it is not normative (ADR 0009 §7)."""
    return dto.Rejected(type="rejected", request_id=request_id, code=rejected_code(result.code), message=result.message)


# --- Decoded commands to engine values (ADR 0009 §6) ---


def betting_action(action: dto.Action, target: int | None) -> Action:
    """The engine action a decoded `act` command names, passed to the engine unchanged.

    The decoder has already checked that a target is present exactly for `bet` and `raise`; `Action` validates that
    pairing again, and the engine alone judges whether the target is legal.
    """
    return Action(WIRE_ACTIONS[action], target)


def showdown_decision(decision: dto.ShowdownDecision) -> ShowdownAction:
    return WIRE_SHOWDOWN_DECISIONS[decision]


def selected_pre_action(kind: dto.PreActionKind, amount: int | None) -> PreAction:
    """The pre-action a decoded `select_pre_action` names; `PreAction` validates the amount for its kind."""
    return PreAction(WIRE_PRE_ACTION_KINDS[kind], amount)
