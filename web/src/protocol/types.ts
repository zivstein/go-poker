/**
 * Hand-written TypeScript types for every ADR 0009 (go-poker.v1) shape.
 *
 * This module has no React and no DOM dependency (C6.2 plan §2.2).
 */

export const PROTOCOL_ID = "go-poker.v1";

export type Card = string;

export type Variant = "texas_holdem";
export type BettingStructure = "no_limit";
export type Phase = "not_started" | "hand_in_progress" | "hand_complete" | "waiting_for_players";
export type Street = "preflop" | "flop" | "turn" | "river";
export type Position = "btn" | "sb" | "bb" | "utg" | "utg1" | "mp" | "lj" | "hj" | "co";
export type Blind = "small" | "big";
export type OccupantStatus = "waiting_to_join" | "sitting_out";
export type TurnKind = "betting" | "showdown";
export type ActionName = "fold" | "check" | "call" | "bet" | "raise";
export type ShowdownKind = "all_in" | "interactive";
export type ShowdownDecision = "show" | "muck";
export type HandCategory =
  | "high_card"
  | "one_pair"
  | "two_pair"
  | "three_of_a_kind"
  | "straight"
  | "flush"
  | "full_house"
  | "four_of_a_kind"
  | "straight_flush";
export type PreActionKind = "check" | "check_or_fold" | "fold" | "call_current";
export type SnapshotCause =
  | "connected"
  | "private"
  | "command"
  | "leave_auto_action"
  | "pre_action"
  | "hand_boundary"
  | "resume";

export interface Settings {
  variant: Variant;
  betting_structure: BettingStructure;
  small_blind: number;
  big_blind: number;
  buy_in: number;
  max_seats: number;
}

export interface Occupant {
  display_name: string;
  is_host: boolean;
  stack: number;
  status: OccupantStatus | null;
}

export interface Seat {
  seat: number;
  occupant: Occupant | null;
}

export interface Strength {
  category: HandCategory;
  description: string;
  cards: Card[];
}

export interface Participant {
  seat: number;
  position: Position;
  blind: Blind | null;
  in_front: number;
  folded: boolean;
  all_in: boolean;
  has_live_cards: boolean;
  hole_cards: Card[] | null;
  hidden_card_count: number;
  strength: Strength | null;
}

export interface Pot {
  amount: number;
  eligible_seats: number[];
}

export interface Turn {
  seat: number;
  kind: TurnKind;
}

export interface LegalActions {
  can_fold: boolean;
  can_check: boolean;
  can_call: boolean;
  amount_owed: number;
  call_amount: number;
  call_is_all_in: boolean;
  can_bet: boolean;
  can_raise: boolean;
  min_full_target: number | null;
  max_target: number | null;
  short_all_in_target: number | null;
}

export interface ShowdownDecisionEntry {
  seat: number;
  decision: ShowdownDecision;
}

export interface Showdown {
  kind: ShowdownKind;
  order: number[];
  decisions: ShowdownDecisionEntry[];
}

export interface PotShare {
  seat: number;
  amount: number;
}

export interface PotAward {
  amount: number;
  eligible_seats: number[];
  shares: PotShare[];
}

export interface ShownRank {
  seat: number;
  category: HandCategory;
}

export interface Settlement {
  pot_awards: PotAward[];
  shown_ranks: ShownRank[];
}

export interface PreAction {
  kind: PreActionKind;
  amount: number | null;
}

export interface HandStartedParticipant {
  seat: number;
  position: Position;
  blind: Blind | null;
  starting_stack: number;
}

export interface BlindPost {
  seat: number;
  blind: Blind;
  chips: number;
  all_in: boolean;
}

export type LogEvent =
  | { event: "hand_started"; number: number; participants: HandStartedParticipant[] }
  | { event: "blinds_posted"; posts: BlindPost[] }
  | { event: "hole_cards_dealt"; own_cards: Card[] | null }
  | { event: "street_dealt"; street: Street; cards: Card[] }
  | { event: "betting_round_started"; street: Street }
  | {
      event: "action_taken";
      seat: number;
      action: ActionName;
      target: number | null;
      chips: number;
      all_in: boolean;
    }
  | { event: "chips_returned"; seat: number; chips: number }
  | { event: "betting_round_completed"; street: Street }
  | { event: "showdown_started"; kind: ShowdownKind; order: number[] }
  | { event: "showdown_decided"; seat: number; decision: ShowdownDecision }
  | { event: "hand_settled"; settlement: Settlement };

export interface Hand {
  number: number;
  street: Street;
  board: Card[];
  participants: Participant[];
  pots: Pot[];
  turn: Turn | null;
  legal_actions: LegalActions | null;
  showdown_actions: ["show", "muck"] | null;
  showdown: Showdown | null;
  settlement: Settlement | null;
  log: LogEvent[];
}

export interface You {
  seat: number;
  is_host: boolean;
  pending_leave: boolean;
  pending_sit_out: boolean;
  pre_action: PreAction | null;
  pre_action_options: PreAction[];
}

export interface TableView {
  table_id: string;
  join_code: string;
  settings: Settings;
  phase: Phase;
  seats: Seat[];
  hand: Hand | null;
  you: You;
}

// --- Server -> client messages (ADR 0009 §7) ---

export type RejectionCode =
  | "STALE_REVISION"
  | "NOT_A_MEMBER"
  | "NOT_HOST"
  | "GAME_ALREADY_STARTED"
  | "NOT_ENOUGH_PLAYERS"
  | "NO_HAND_IN_PROGRESS"
  | "NOT_YOUR_TURN"
  | "ILLEGAL_ACTION"
  | "LEAVE_PENDING"
  | "NO_CHANGE"
  | "PRE_ACTION_UNAVAILABLE";

export type ErrorCode =
  | "MALFORMED_MESSAGE"
  | "INVALID_COMMAND"
  | "HELLO_REQUIRED"
  | "PROTOCOL_MISMATCH"
  | "AUTH_FAILED"
  | "HELLO_TIMEOUT";

export interface SnapshotMessage {
  type: "snapshot";
  revision: number;
  cause: SnapshotCause;
  view: TableView;
}

export interface AcceptedMessage {
  type: "accepted";
  request_id: string;
  revision: number;
}

export interface RejectedMessage {
  type: "rejected";
  request_id: string;
  code: RejectionCode;
  message: string;
}

export interface ErrorMessage {
  type: "error";
  request_id: string | null;
  code: ErrorCode;
  message: string;
}

export interface SupersededMessage {
  type: "superseded";
}

export interface LeftTableMessage {
  type: "left_table";
}

export interface TableFailedMessage {
  type: "table_failed";
}

export type ServerMessage =
  | SnapshotMessage
  | AcceptedMessage
  | RejectedMessage
  | ErrorMessage
  | SupersededMessage
  | LeftTableMessage
  | TableFailedMessage;

// --- Client -> server messages (ADR 0009 §5, §6) ---

export interface HelloMessage {
  type: "hello";
  protocol: "go-poker.v1";
  credential: string;
}

export type ActArgs =
  | { action: "fold" | "check" | "call"; target: null }
  | { action: "bet" | "raise"; target: number };

export type CommandPayload =
  | { name: "start_game"; args: Record<string, never> }
  | { name: "act"; args: ActArgs }
  | { name: "showdown_decision"; args: { decision: ShowdownDecision } }
  | { name: "sit_out"; args: Record<string, never> }
  | { name: "sit_back"; args: Record<string, never> }
  | { name: "leave"; args: Record<string, never> }
  | { name: "select_pre_action"; args: { pre_action: PreAction } }
  | { name: "clear_pre_action"; args: Record<string, never> };

export type CommandName = CommandPayload["name"];

export type CommandMessage = {
  type: "command";
  request_id: string;
  expected_revision: number;
} & CommandPayload;

export type ClientMessage = HelloMessage | CommandMessage;

// --- HTTP (ADR 0009 §4) ---

export type HttpErrorCode =
  | "VALIDATION_FAILED"
  | "TABLE_NOT_FOUND"
  | "DISPLAY_NAME_TAKEN"
  | "SEAT_TAKEN"
  | "INVALID_SEAT"
  | "ALREADY_MEMBER"
  | "LEFT_TABLE"
  | "INTERNAL_ERROR";

export interface HttpErrorBody {
  error: {
    code: HttpErrorCode;
    message: string;
    field: string | null;
  };
}

export interface CreateTableRequestBody {
  display_name: string;
}

export interface CreateTableResponseBody {
  table_id: string;
  join_code: string;
  seat: number;
  credential: string;
}

export interface JoinTableRequestBody {
  display_name: string;
  seat: number;
}

export interface JoinTableResponseBody {
  table_id: string;
  seat: number;
  credential: string;
}
