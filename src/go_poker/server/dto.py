"""The `go-poker.v1` wire models: every server message, the view it carries, and the HTTP bodies (ADR 0009).

The protocol is closed (ADR 0009 §1.3), so every model decodes and encodes strictly:

- `extra="forbid"`: an unknown field is an error;
- `strict=True`: a boolean is not an integer and a float is not an integer;
- `frozen=True`: a built message is a value;
- every field is always present. An absent value is `None`, never an omitted key (ADR 0009 §2), so nothing is
  serialized conditionally and no field has a default that would let a key vanish.

Every wire enum is a `Literal` alias of its lowercase (or `UPPER_SNAKE`, for codes) strings, never a Python enum: the
wire strings are the protocol's, and the explicit tables in `mapping` are the only place an engine value becomes one
(ADR 0009 §3, §12). Keeping them out of the models also makes `strict=True` exact, because a `Literal` accepts nothing
but the listed strings.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# --- Wire enums (ADR 0009 §3, §12) ---

Variant = Literal["texas_holdem"]
BettingStructure = Literal["no_limit"]
Phase = Literal["not_started", "hand_in_progress", "hand_complete", "waiting_for_players"]
Street = Literal["preflop", "flop", "turn", "river"]
Position = Literal["btn", "sb", "bb", "utg", "utg1", "mp", "lj", "hj", "co"]
Blind = Literal["small", "big"]
OccupantStatus = Literal["waiting_to_join", "sitting_out"]
TurnKind = Literal["betting", "showdown"]
Action = Literal["fold", "check", "call", "bet", "raise"]
ShowdownKind = Literal["all_in", "interactive"]
ShowdownDecision = Literal["show", "muck"]
HandCategory = Literal[
    "high_card",
    "one_pair",
    "two_pair",
    "three_of_a_kind",
    "straight",
    "flush",
    "full_house",
    "four_of_a_kind",
    "straight_flush",
]
PreActionKind = Literal["check", "check_or_fold", "fold", "call_current"]
SnapshotCause = Literal["connected", "private", "command", "leave_auto_action", "pre_action", "hand_boundary", "resume"]
RejectedCode = Literal[
    "STALE_REVISION",
    "NOT_A_MEMBER",
    "NOT_HOST",
    "GAME_ALREADY_STARTED",
    "NOT_ENOUGH_PLAYERS",
    "NO_HAND_IN_PROGRESS",
    "NOT_YOUR_TURN",
    "ILLEGAL_ACTION",
    "LEAVE_PENDING",
    "NO_CHANGE",
    "PRE_ACTION_UNAVAILABLE",
]
ErrorCode = Literal[
    "MALFORMED_MESSAGE",
    "INVALID_COMMAND",
    "HELLO_REQUIRED",
    "PROTOCOL_MISMATCH",
    "AUTH_FAILED",
    "HELLO_TIMEOUT",
]
HttpErrorCode = Literal[
    "VALIDATION_FAILED",
    "TABLE_NOT_FOUND",
    "DISPLAY_NAME_TAKEN",
    "SEAT_TAKEN",
    "INVALID_SEAT",
    "ALREADY_MEMBER",
    "LEFT_TABLE",
    "INTERNAL_ERROR",
]

# A card is two characters, rank then suit (ADR 0009 §3). It is a plain string on the wire; `mapping` encodes it.
Card = str


class WireModel(BaseModel):
    """The strict, frozen base of every wire model. Its configuration is the protocol's decoding rules."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


# --- The view (ADR 0009 §10, §11) ---


class Settings(WireModel):
    variant: Variant
    betting_structure: BettingStructure
    small_blind: int
    big_blind: int
    buy_in: int
    max_seats: int


class Occupant(WireModel):
    display_name: str
    is_host: bool
    stack: int
    status: OccupantStatus | None


class Seat(WireModel):
    seat: int
    occupant: Occupant | None


class Strength(WireModel):
    category: HandCategory
    description: str
    cards: list[Card]


class Participant(WireModel):
    seat: int
    position: Position
    blind: Blind | None
    in_front: int
    folded: bool
    all_in: bool
    has_live_cards: bool
    hole_cards: list[Card] | None
    hidden_card_count: int
    strength: Strength | None


class Pot(WireModel):
    amount: int
    eligible_seats: list[int]


class Turn(WireModel):
    seat: int
    kind: TurnKind


class LegalActions(WireModel):
    can_fold: bool
    can_check: bool
    can_call: bool
    amount_owed: int
    call_amount: int
    call_is_all_in: bool
    can_bet: bool
    can_raise: bool
    min_full_target: int | None
    max_target: int | None
    short_all_in_target: int | None


class SeatDecision(WireModel):
    seat: int
    decision: ShowdownDecision


class Showdown(WireModel):
    kind: ShowdownKind
    order: list[int]
    decisions: list[SeatDecision]


class Share(WireModel):
    seat: int
    amount: int


class PotAward(WireModel):
    amount: int
    eligible_seats: list[int]
    shares: list[Share]


class ShownRank(WireModel):
    seat: int
    category: HandCategory


class Settlement(WireModel):
    pot_awards: list[PotAward]
    shown_ranks: list[ShownRank]


class PreAction(WireModel):
    kind: PreActionKind
    amount: int | None


# --- Log events (ADR 0009 §10) ---


class LogParticipant(WireModel):
    seat: int
    position: Position
    blind: Blind | None
    starting_stack: int


class HandStartedEvent(WireModel):
    event: Literal["hand_started"]
    number: int
    participants: list[LogParticipant]


class BlindPost(WireModel):
    seat: int
    blind: Blind
    chips: int
    all_in: bool


class BlindsPostedEvent(WireModel):
    event: Literal["blinds_posted"]
    posts: list[BlindPost]


class HoleCardsDealtEvent(WireModel):
    event: Literal["hole_cards_dealt"]
    own_cards: list[Card] | None


class StreetDealtEvent(WireModel):
    event: Literal["street_dealt"]
    street: Street
    cards: list[Card]


class BettingRoundStartedEvent(WireModel):
    event: Literal["betting_round_started"]
    street: Street


class ActionTakenEvent(WireModel):
    event: Literal["action_taken"]
    seat: int
    action: Action
    target: int | None
    chips: int
    all_in: bool


class ChipsReturnedEvent(WireModel):
    event: Literal["chips_returned"]
    seat: int
    chips: int


class BettingRoundCompletedEvent(WireModel):
    event: Literal["betting_round_completed"]
    street: Street


class ShowdownStartedEvent(WireModel):
    event: Literal["showdown_started"]
    kind: ShowdownKind
    order: list[int]


class ShowdownDecidedEvent(WireModel):
    event: Literal["showdown_decided"]
    seat: int
    decision: ShowdownDecision


class HandSettledEvent(WireModel):
    event: Literal["hand_settled"]
    settlement: Settlement


LogEvent = Annotated[
    HandStartedEvent
    | BlindsPostedEvent
    | HoleCardsDealtEvent
    | StreetDealtEvent
    | BettingRoundStartedEvent
    | ActionTakenEvent
    | ChipsReturnedEvent
    | BettingRoundCompletedEvent
    | ShowdownStartedEvent
    | ShowdownDecidedEvent
    | HandSettledEvent,
    Field(discriminator="event"),
]


class Hand(WireModel):
    number: int
    street: Street
    board: list[Card]
    participants: list[Participant]
    pots: list[Pot]
    turn: Turn | None
    legal_actions: LegalActions | None
    showdown_actions: list[ShowdownDecision] | None
    showdown: Showdown | None
    settlement: Settlement | None
    log: list[LogEvent]


class You(WireModel):
    seat: int
    is_host: bool
    pending_leave: bool
    pending_sit_out: bool
    pre_action: PreAction | None
    pre_action_options: list[PreAction]


class View(WireModel):
    table_id: str
    join_code: str
    settings: Settings
    phase: Phase
    seats: list[Seat]
    hand: Hand | None
    you: You


# --- Server messages (ADR 0009 §7) ---


class Snapshot(WireModel):
    type: Literal["snapshot"]
    revision: int
    cause: SnapshotCause
    view: View


class Accepted(WireModel):
    type: Literal["accepted"]
    request_id: str
    revision: int


class Rejected(WireModel):
    type: Literal["rejected"]
    request_id: str
    code: RejectedCode
    message: str


class ErrorMessage(WireModel):
    type: Literal["error"]
    request_id: str | None
    code: ErrorCode
    message: str


class Superseded(WireModel):
    type: Literal["superseded"]


class LeftTable(WireModel):
    type: Literal["left_table"]


class TableFailed(WireModel):
    type: Literal["table_failed"]


ServerMessage = Annotated[
    Snapshot | Accepted | Rejected | ErrorMessage | Superseded | LeftTable | TableFailed,
    Field(discriminator="type"),
]


# --- HTTP bodies (ADR 0009 §4) ---


class CreateTableRequest(WireModel):
    display_name: str


class JoinTableRequest(WireModel):
    display_name: str
    # The product's seat range (ADR 0009 §4). A seat above this table's own `max_seats` is the engine's decision,
    # answered with `INVALID_SEAT`, so the body check is the range and nothing more.
    seat: Annotated[int, Field(ge=1, le=9)]


class CreateTableResponse(WireModel):
    table_id: str
    join_code: str
    seat: int
    credential: str


class JoinTableResponse(WireModel):
    table_id: str
    seat: int
    credential: str


class ErrorDetail(WireModel):
    code: HttpErrorCode
    message: str
    field: str | None


class ErrorBody(WireModel):
    error: ErrorDetail


# --- JSON Schema ---

_SERVER_MESSAGE_ADAPTER: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)


def wire_schema() -> dict[str, object]:
    """The JSON Schema of every `go-poker.v1` server message, derived from these models.

    It is not a second source beside them (ADR 0009, Alternatives considered): it is exported so that a test can read
    it and the Friends Alpha can generate client types from it (W6).
    """
    return dict(_SERVER_MESSAGE_ADAPTER.json_schema())
