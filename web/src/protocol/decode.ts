/**
 * Strict decoders for every ADR 0009 (go-poker.v1) shape.
 *
 * Decoding rejects an unknown `type`, command `name` or enum value; a missing
 * or extra field; a value of the wrong JSON type; an out-of-range integer;
 * and a card outside the ADR 0009 §3 encoding. No value is ever guessed.
 */

import type {
  ActArgs,
  BlindPost,
  CommandMessage,
  CommandName,
  CommandPayload,
  CreateTableResponseBody,
  ErrorCode,
  Hand,
  HandCategory,
  HandStartedParticipant,
  HttpErrorBody,
  HttpErrorCode,
  JoinTableResponseBody,
  LegalActions,
  LogEvent,
  Occupant,
  OccupantStatus,
  Participant,
  Pot,
  PotAward,
  PotShare,
  PreAction,
  RejectionCode,
  Seat,
  ServerMessage,
  Settings,
  Settlement,
  ShowdownDecisionEntry,
  ShownRank,
  Strength,
  TableView,
  Turn,
  You,
} from "./types";

export class ProtocolDecodeError extends Error {
  constructor(path: string, message: string) {
    super(`${path}: ${message}`);
    this.name = "ProtocolDecodeError";
  }
}

function fail(path: string, message: string): never {
  throw new ProtocolDecodeError(path, message);
}

const FLOAT_SENTINEL_PREFIX = "\u0000FLOAT:";
const FLOAT_SENTINEL_SUFFIX = "\u0000";
// Built from a string, not a literal: a literal control character in a regex
// literal trips Biome's noControlCharactersInRegex lint.
const FLOAT_SENTINEL_RE = new RegExp(`^${FLOAT_SENTINEL_PREFIX}(.+)${FLOAT_SENTINEL_SUFFIX}$`);
// Matches a JSON string literal (left untouched) or a bare float-looking number
// literal (one with a decimal point or an exponent) outside of a string.
const STRING_OR_FLOAT_LITERAL =
  /"(?:[^"\\]|\\.)*"|(-?\d+\.\d+(?:[eE][+-]?\d+)?|-?\d+[eE][+-]?\d+)/g;

/**
 * Parses a wire JSON frame, preserving whether a number literal was written
 * with a decimal point or exponent. `JSON.parse` alone cannot tell `10` from
 * `10.0`: both become the number `10`. ADR 0009 §2 requires rejecting `10.0`
 * for an integer field, so every float-looking literal is parsed instead as a
 * sentinel string that `expectInt` recognizes and rejects.
 */
export function parseWireJson(text: string): unknown {
  const marked = text.replace(
    STRING_OR_FLOAT_LITERAL,
    (whole, floatLiteral: string | undefined) => {
      if (floatLiteral === undefined) return whole; // a string literal; left untouched
      return JSON.stringify(`${FLOAT_SENTINEL_PREFIX}${floatLiteral}${FLOAT_SENTINEL_SUFFIX}`);
    },
  );
  return JSON.parse(marked);
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Checks the object has exactly this key set: no missing, no extra field. */
function expectKeys(obj: Record<string, unknown>, keys: readonly string[], path: string): void {
  const have = Object.keys(obj);
  for (const key of keys) {
    if (!(key in obj)) fail(path, `missing field "${key}"`);
  }
  for (const key of have) {
    if (!keys.includes(key)) fail(path, `unexpected field "${key}"`);
  }
}

function expectObject(
  value: unknown,
  keys: readonly string[],
  path: string,
): Record<string, unknown> {
  if (!isPlainObject(value)) fail(path, "expected an object");
  expectKeys(value, keys, path);
  return value;
}

function expectString(value: unknown, path: string): string {
  if (typeof value !== "string") fail(path, "expected a string");
  // A float-looking number literal was turned into a sentinel string by
  // parseWireJson; it is a number on the wire, never a string.
  if (value.startsWith(FLOAT_SENTINEL_PREFIX)) fail(path, "expected a string, not a number");
  return value;
}

function expectBool(value: unknown, path: string): boolean {
  if (typeof value !== "boolean") fail(path, "expected a boolean");
  return value;
}

function expectInt(value: unknown, path: string, min?: number): number {
  if (typeof value === "string" && FLOAT_SENTINEL_RE.test(value)) {
    fail(path, `expected an integer, not a float (${FLOAT_SENTINEL_RE.exec(value)?.[1]})`);
  }
  if (typeof value !== "number" || !Number.isFinite(value)) fail(path, "expected a number");
  if (!Number.isInteger(value)) fail(path, "expected an integer");
  if (!Number.isSafeInteger(value)) fail(path, "integer out of range");
  if (min !== undefined && value < min) fail(path, `expected an integer ≥ ${min}`);
  return value;
}

const REQUEST_ID_RE = /^[A-Za-z0-9_-]{1,64}$/;

function expectRequestId(value: unknown, path: string): string {
  const s = expectString(value, path);
  if (!REQUEST_ID_RE.test(s)) fail(path, "invalid request_id format");
  return s;
}

function expectMoney(value: unknown, path: string): number {
  return expectInt(value, path, 0);
}

function expectSeatNumber(value: unknown, path: string): number {
  // The product range is seats 1-9 (ADR 0009 §4).
  const n = expectInt(value, path, 1);
  if (n > 9) fail(path, "seat number out of range");
  return n;
}

function expectNullOr<T>(
  value: unknown,
  path: string,
  decode: (v: unknown, path: string) => T,
): T | null {
  if (value === null) return null;
  return decode(value, path);
}

function expectEnum<T extends string>(value: unknown, allowed: readonly T[], path: string): T {
  const s = expectString(value, path);
  if (!(allowed as readonly string[]).includes(s)) fail(path, `unknown value "${s}"`);
  return s as T;
}

function expectArray<T>(
  value: unknown,
  path: string,
  decode: (v: unknown, path: string) => T,
): T[] {
  if (!Array.isArray(value)) fail(path, "expected an array");
  return value.map((item, i) => decode(item, `${path}[${i}]`));
}

const RANKS = "23456789TJQKA";
const SUITS = "cdhs";

function expectCard(value: unknown, path: string): string {
  const s = expectString(value, path);
  if (s.length !== 2 || !RANKS.includes(s[0] as string) || !SUITS.includes(s[1] as string)) {
    fail(path, `invalid card "${s}"`);
  }
  return s;
}

const VARIANTS = ["texas_holdem"] as const;
const BETTING_STRUCTURES = ["no_limit"] as const;
const PHASES = ["not_started", "hand_in_progress", "hand_complete", "waiting_for_players"] as const;
const STREETS = ["preflop", "flop", "turn", "river"] as const;
const POSITIONS = ["btn", "sb", "bb", "utg", "utg1", "mp", "lj", "hj", "co"] as const;
const BLINDS = ["small", "big"] as const;
const OCCUPANT_STATUSES = ["waiting_to_join", "sitting_out"] as const;
const TURN_KINDS = ["betting", "showdown"] as const;
const ACTION_NAMES = ["fold", "check", "call", "bet", "raise"] as const;
const SHOWDOWN_KINDS = ["all_in", "interactive"] as const;
const SHOWDOWN_DECISIONS = ["show", "muck"] as const;
const HAND_CATEGORIES = [
  "high_card",
  "one_pair",
  "two_pair",
  "three_of_a_kind",
  "straight",
  "flush",
  "full_house",
  "four_of_a_kind",
  "straight_flush",
] as const satisfies readonly HandCategory[];
const SNAPSHOT_CAUSES = [
  "connected",
  "private",
  "command",
  "leave_auto_action",
  "pre_action",
  "hand_boundary",
  "resume",
] as const;
const REJECTION_CODES = [
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
] as const satisfies readonly RejectionCode[];
const ERROR_CODES = [
  "MALFORMED_MESSAGE",
  "INVALID_COMMAND",
  "HELLO_REQUIRED",
  "PROTOCOL_MISMATCH",
  "AUTH_FAILED",
  "HELLO_TIMEOUT",
] as const satisfies readonly ErrorCode[];
const HTTP_ERROR_CODES = [
  "VALIDATION_FAILED",
  "TABLE_NOT_FOUND",
  "DISPLAY_NAME_TAKEN",
  "SEAT_TAKEN",
  "INVALID_SEAT",
  "ALREADY_MEMBER",
  "LEFT_TABLE",
  "INTERNAL_ERROR",
] as const satisfies readonly HttpErrorCode[];

function decodeSettings(value: unknown, path: string): Settings {
  const o = expectObject(
    value,
    ["variant", "betting_structure", "small_blind", "big_blind", "buy_in", "max_seats"],
    path,
  );
  const maxSeats = expectInt(o.max_seats, `${path}.max_seats`, 2);
  if (maxSeats > 9) fail(`${path}.max_seats`, "expected an integer ≤ 9");
  return {
    variant: expectEnum(o.variant, VARIANTS, `${path}.variant`),
    betting_structure: expectEnum(
      o.betting_structure,
      BETTING_STRUCTURES,
      `${path}.betting_structure`,
    ),
    small_blind: expectInt(o.small_blind, `${path}.small_blind`, 1),
    big_blind: expectInt(o.big_blind, `${path}.big_blind`, 1),
    buy_in: expectInt(o.buy_in, `${path}.buy_in`, 1),
    max_seats: maxSeats,
  };
}

function decodeOccupant(value: unknown, path: string): Occupant {
  const o = expectObject(value, ["display_name", "is_host", "stack", "status"], path);
  return {
    display_name: expectString(o.display_name, `${path}.display_name`),
    is_host: expectBool(o.is_host, `${path}.is_host`),
    stack: expectMoney(o.stack, `${path}.stack`),
    status: expectNullOr<OccupantStatus>(o.status, `${path}.status`, (v, p) =>
      expectEnum(v, OCCUPANT_STATUSES, p),
    ),
  };
}

function decodeSeat(value: unknown, path: string): Seat {
  const o = expectObject(value, ["seat", "occupant"], path);
  return {
    seat: expectSeatNumber(o.seat, `${path}.seat`),
    occupant: expectNullOr(o.occupant, `${path}.occupant`, decodeOccupant),
  };
}

function decodeStrength(value: unknown, path: string): Strength {
  const o = expectObject(value, ["category", "description", "cards"], path);
  const cards = expectArray(o.cards, `${path}.cards`, expectCard);
  if (cards.length !== 5) fail(`${path}.cards`, "expected exactly 5 cards");
  return {
    category: expectEnum(o.category, HAND_CATEGORIES, `${path}.category`),
    description: expectString(o.description, `${path}.description`),
    cards,
  };
}

function decodeParticipant(value: unknown, path: string): Participant {
  const o = expectObject(
    value,
    [
      "seat",
      "position",
      "blind",
      "in_front",
      "folded",
      "all_in",
      "has_live_cards",
      "hole_cards",
      "hidden_card_count",
      "strength",
    ],
    path,
  );
  return {
    seat: expectSeatNumber(o.seat, `${path}.seat`),
    position: expectEnum(o.position, POSITIONS, `${path}.position`),
    blind: expectNullOr(o.blind, `${path}.blind`, (v, p) => expectEnum(v, BLINDS, p)),
    in_front: expectMoney(o.in_front, `${path}.in_front`),
    folded: expectBool(o.folded, `${path}.folded`),
    all_in: expectBool(o.all_in, `${path}.all_in`),
    has_live_cards: expectBool(o.has_live_cards, `${path}.has_live_cards`),
    hole_cards: expectNullOr(o.hole_cards, `${path}.hole_cards`, (v, p) =>
      expectArray(v, p, expectCard),
    ),
    hidden_card_count: expectInt(o.hidden_card_count, `${path}.hidden_card_count`, 0),
    strength: expectNullOr(o.strength, `${path}.strength`, decodeStrength),
  };
}

function decodePot(value: unknown, path: string): Pot {
  const o = expectObject(value, ["amount", "eligible_seats"], path);
  return {
    amount: expectInt(o.amount, `${path}.amount`, 1),
    eligible_seats: expectArray(o.eligible_seats, `${path}.eligible_seats`, expectSeatNumber),
  };
}

function decodeTurn(value: unknown, path: string): Turn {
  const o = expectObject(value, ["seat", "kind"], path);
  return {
    seat: expectSeatNumber(o.seat, `${path}.seat`),
    kind: expectEnum(o.kind, TURN_KINDS, `${path}.kind`),
  };
}

function decodeLegalActions(value: unknown, path: string): LegalActions {
  const o = expectObject(
    value,
    [
      "can_fold",
      "can_check",
      "can_call",
      "amount_owed",
      "call_amount",
      "call_is_all_in",
      "can_bet",
      "can_raise",
      "min_full_target",
      "max_target",
      "short_all_in_target",
    ],
    path,
  );
  return {
    can_fold: expectBool(o.can_fold, `${path}.can_fold`),
    can_check: expectBool(o.can_check, `${path}.can_check`),
    can_call: expectBool(o.can_call, `${path}.can_call`),
    amount_owed: expectMoney(o.amount_owed, `${path}.amount_owed`),
    call_amount: expectMoney(o.call_amount, `${path}.call_amount`),
    call_is_all_in: expectBool(o.call_is_all_in, `${path}.call_is_all_in`),
    can_bet: expectBool(o.can_bet, `${path}.can_bet`),
    can_raise: expectBool(o.can_raise, `${path}.can_raise`),
    min_full_target: expectNullOr(o.min_full_target, `${path}.min_full_target`, (v, p) =>
      expectInt(v, p, 1),
    ),
    max_target: expectNullOr(o.max_target, `${path}.max_target`, (v, p) => expectInt(v, p, 1)),
    short_all_in_target: expectNullOr(
      o.short_all_in_target,
      `${path}.short_all_in_target`,
      (v, p) => expectInt(v, p, 1),
    ),
  };
}

function decodeShowdownDecisionEntry(value: unknown, path: string): ShowdownDecisionEntry {
  const o = expectObject(value, ["seat", "decision"], path);
  return {
    seat: expectSeatNumber(o.seat, `${path}.seat`),
    decision: expectEnum(o.decision, SHOWDOWN_DECISIONS, `${path}.decision`),
  };
}

function decodeShowdown(value: unknown, path: string): import("./types").Showdown {
  const o = expectObject(value, ["kind", "order", "decisions"], path);
  return {
    kind: expectEnum(o.kind, SHOWDOWN_KINDS, `${path}.kind`),
    order: expectArray(o.order, `${path}.order`, expectSeatNumber),
    decisions: expectArray(o.decisions, `${path}.decisions`, decodeShowdownDecisionEntry),
  };
}

function decodePotShare(value: unknown, path: string): PotShare {
  const o = expectObject(value, ["seat", "amount"], path);
  return {
    seat: expectSeatNumber(o.seat, `${path}.seat`),
    amount: expectMoney(o.amount, `${path}.amount`),
  };
}

function decodePotAward(value: unknown, path: string): PotAward {
  const o = expectObject(value, ["amount", "eligible_seats", "shares"], path);
  return {
    amount: expectMoney(o.amount, `${path}.amount`),
    eligible_seats: expectArray(o.eligible_seats, `${path}.eligible_seats`, expectSeatNumber),
    shares: expectArray(o.shares, `${path}.shares`, decodePotShare),
  };
}

function decodeShownRank(value: unknown, path: string): ShownRank {
  const o = expectObject(value, ["seat", "category"], path);
  return {
    seat: expectSeatNumber(o.seat, `${path}.seat`),
    category: expectEnum(o.category, HAND_CATEGORIES, `${path}.category`),
  };
}

function decodeSettlement(value: unknown, path: string): Settlement {
  const o = expectObject(value, ["pot_awards", "shown_ranks"], path);
  return {
    pot_awards: expectArray(o.pot_awards, `${path}.pot_awards`, decodePotAward),
    shown_ranks: expectArray(o.shown_ranks, `${path}.shown_ranks`, decodeShownRank),
  };
}

const PRE_ACTION_KINDS = ["check", "check_or_fold", "fold", "call_current"] as const;

function decodePreAction(value: unknown, path: string): PreAction {
  const o = expectObject(value, ["kind", "amount"], path);
  const kind = expectEnum(o.kind, PRE_ACTION_KINDS, `${path}.kind`);
  const amount = expectNullOr(o.amount, `${path}.amount`, (v, p) => expectInt(v, p, 1));
  if (kind === "call_current" && amount === null) {
    fail(`${path}.amount`, "call_current requires an amount");
  }
  if (kind !== "call_current" && amount !== null) {
    fail(`${path}.amount`, "amount is set only for call_current");
  }
  return { kind, amount };
}

function decodeHandStartedParticipant(value: unknown, path: string): HandStartedParticipant {
  const o = expectObject(value, ["seat", "position", "blind", "starting_stack"], path);
  return {
    seat: expectSeatNumber(o.seat, `${path}.seat`),
    position: expectEnum(o.position, POSITIONS, `${path}.position`),
    blind: expectNullOr(o.blind, `${path}.blind`, (v, p) => expectEnum(v, BLINDS, p)),
    starting_stack: expectMoney(o.starting_stack, `${path}.starting_stack`),
  };
}

function decodeBlindPost(value: unknown, path: string): BlindPost {
  const o = expectObject(value, ["seat", "blind", "chips", "all_in"], path);
  return {
    seat: expectSeatNumber(o.seat, `${path}.seat`),
    blind: expectEnum(o.blind, BLINDS, `${path}.blind`),
    chips: expectMoney(o.chips, `${path}.chips`),
    all_in: expectBool(o.all_in, `${path}.all_in`),
  };
}

function decodeLogEvent(value: unknown, path: string): LogEvent {
  if (!isPlainObject(value)) fail(path, "expected an object");
  const event = expectString(value.event, `${path}.event`);
  switch (event) {
    case "hand_started": {
      const o = expectObject(value, ["event", "number", "participants"], path);
      return {
        event: "hand_started",
        number: expectInt(o.number, `${path}.number`, 1),
        participants: expectArray(
          o.participants,
          `${path}.participants`,
          decodeHandStartedParticipant,
        ),
      };
    }
    case "blinds_posted": {
      const o = expectObject(value, ["event", "posts"], path);
      return {
        event: "blinds_posted",
        posts: expectArray(o.posts, `${path}.posts`, decodeBlindPost),
      };
    }
    case "hole_cards_dealt": {
      const o = expectObject(value, ["event", "own_cards"], path);
      return {
        event: "hole_cards_dealt",
        own_cards: expectNullOr(o.own_cards, `${path}.own_cards`, (v, p) =>
          expectArray(v, p, expectCard),
        ),
      };
    }
    case "street_dealt": {
      const o = expectObject(value, ["event", "street", "cards"], path);
      return {
        event: "street_dealt",
        street: expectEnum(o.street, STREETS, `${path}.street`),
        cards: expectArray(o.cards, `${path}.cards`, expectCard),
      };
    }
    case "betting_round_started": {
      const o = expectObject(value, ["event", "street"], path);
      return {
        event: "betting_round_started",
        street: expectEnum(o.street, STREETS, `${path}.street`),
      };
    }
    case "action_taken": {
      const o = expectObject(value, ["event", "seat", "action", "target", "chips", "all_in"], path);
      const action = expectEnum(o.action, ACTION_NAMES, `${path}.action`);
      const target = expectNullOr(o.target, `${path}.target`, (v, p) => expectInt(v, p, 1));
      if ((action === "bet" || action === "raise") && target === null) {
        fail(`${path}.target`, "bet and raise require a target");
      }
      if (action !== "bet" && action !== "raise" && target !== null) {
        fail(`${path}.target`, "target is set only for bet and raise");
      }
      return {
        event: "action_taken",
        seat: expectSeatNumber(o.seat, `${path}.seat`),
        action,
        target,
        chips: expectMoney(o.chips, `${path}.chips`),
        all_in: expectBool(o.all_in, `${path}.all_in`),
      };
    }
    case "chips_returned": {
      const o = expectObject(value, ["event", "seat", "chips"], path);
      return {
        event: "chips_returned",
        seat: expectSeatNumber(o.seat, `${path}.seat`),
        chips: expectMoney(o.chips, `${path}.chips`),
      };
    }
    case "betting_round_completed": {
      const o = expectObject(value, ["event", "street"], path);
      return {
        event: "betting_round_completed",
        street: expectEnum(o.street, STREETS, `${path}.street`),
      };
    }
    case "showdown_started": {
      const o = expectObject(value, ["event", "kind", "order"], path);
      return {
        event: "showdown_started",
        kind: expectEnum(o.kind, SHOWDOWN_KINDS, `${path}.kind`),
        order: expectArray(o.order, `${path}.order`, expectSeatNumber),
      };
    }
    case "showdown_decided": {
      const o = expectObject(value, ["event", "seat", "decision"], path);
      return {
        event: "showdown_decided",
        seat: expectSeatNumber(o.seat, `${path}.seat`),
        decision: expectEnum(o.decision, SHOWDOWN_DECISIONS, `${path}.decision`),
      };
    }
    case "hand_settled": {
      const o = expectObject(value, ["event", "settlement"], path);
      return {
        event: "hand_settled",
        settlement: decodeSettlement(o.settlement, `${path}.settlement`),
      };
    }
    default:
      fail(`${path}.event`, `unknown event "${event}"`);
  }
}

function decodeHand(value: unknown, path: string): Hand {
  const o = expectObject(
    value,
    [
      "number",
      "street",
      "board",
      "participants",
      "pots",
      "turn",
      "legal_actions",
      "showdown_actions",
      "showdown",
      "settlement",
      "log",
    ],
    path,
  );
  return {
    number: expectInt(o.number, `${path}.number`, 1),
    street: expectEnum(o.street, STREETS, `${path}.street`),
    board: expectArray(o.board, `${path}.board`, expectCard),
    participants: expectArray(o.participants, `${path}.participants`, decodeParticipant),
    pots: expectArray(o.pots, `${path}.pots`, decodePot),
    turn: expectNullOr(o.turn, `${path}.turn`, decodeTurn),
    legal_actions: expectNullOr(o.legal_actions, `${path}.legal_actions`, decodeLegalActions),
    showdown_actions: decodeShowdownActions(o.showdown_actions, `${path}.showdown_actions`),
    showdown: expectNullOr(o.showdown, `${path}.showdown`, decodeShowdown),
    settlement: expectNullOr(o.settlement, `${path}.settlement`, decodeSettlement),
    log: expectArray(o.log, `${path}.log`, decodeLogEvent),
  };
}

function decodeShowdownActions(value: unknown, path: string): ["show", "muck"] | null {
  if (value === null) return null;
  const arr = expectArray(value, path, (v, p) => expectEnum(v, SHOWDOWN_DECISIONS, p));
  if (arr.length !== 2 || arr[0] !== "show" || arr[1] !== "muck") {
    fail(path, 'expected exactly ["show", "muck"]');
  }
  return ["show", "muck"];
}

function decodeYou(value: unknown, path: string): You {
  const o = expectObject(
    value,
    ["seat", "is_host", "pending_leave", "pending_sit_out", "pre_action", "pre_action_options"],
    path,
  );
  return {
    seat: expectSeatNumber(o.seat, `${path}.seat`),
    is_host: expectBool(o.is_host, `${path}.is_host`),
    pending_leave: expectBool(o.pending_leave, `${path}.pending_leave`),
    pending_sit_out: expectBool(o.pending_sit_out, `${path}.pending_sit_out`),
    pre_action: expectNullOr(o.pre_action, `${path}.pre_action`, decodePreAction),
    pre_action_options: expectArray(
      o.pre_action_options,
      `${path}.pre_action_options`,
      decodePreAction,
    ),
  };
}

export function decodeTableView(value: unknown, path = "view"): TableView {
  const o = expectObject(
    value,
    ["table_id", "join_code", "settings", "phase", "seats", "hand", "you"],
    path,
  );
  return {
    table_id: expectString(o.table_id, `${path}.table_id`),
    join_code: expectString(o.join_code, `${path}.join_code`),
    settings: decodeSettings(o.settings, `${path}.settings`),
    phase: expectEnum(o.phase, PHASES, `${path}.phase`),
    seats: expectArray(o.seats, `${path}.seats`, decodeSeat),
    hand: expectNullOr(o.hand, `${path}.hand`, decodeHand),
    you: decodeYou(o.you, `${path}.you`),
  };
}

function decodeSnapshotMessage(o: Record<string, unknown>, path: string): ServerMessage {
  expectKeys(o, ["type", "revision", "cause", "view"], path);
  return {
    type: "snapshot",
    revision: expectInt(o.revision, `${path}.revision`, 1),
    cause: expectEnum(o.cause, SNAPSHOT_CAUSES, `${path}.cause`),
    view: decodeTableView(o.view, `${path}.view`),
  };
}

export function decodeServerMessage(raw: unknown): ServerMessage {
  const o = isPlainObject(raw) ? raw : fail("$", "expected an object");
  const type = expectString(o.type, "$.type");
  switch (type) {
    case "snapshot":
      return decodeSnapshotMessage(o, "$");
    case "accepted": {
      expectKeys(o, ["type", "request_id", "revision"], "$");
      return {
        type: "accepted",
        request_id: expectRequestId(o.request_id, "$.request_id"),
        revision: expectInt(o.revision, "$.revision", 1),
      };
    }
    case "rejected": {
      expectKeys(o, ["type", "request_id", "code", "message"], "$");
      return {
        type: "rejected",
        request_id: expectRequestId(o.request_id, "$.request_id"),
        code: expectEnum(o.code, REJECTION_CODES, "$.code"),
        message: expectString(o.message, "$.message"),
      };
    }
    case "error": {
      expectKeys(o, ["type", "request_id", "code", "message"], "$");
      return {
        type: "error",
        request_id: expectNullOr(o.request_id, "$.request_id", expectRequestId),
        code: expectEnum(o.code, ERROR_CODES, "$.code"),
        message: expectString(o.message, "$.message"),
      };
    }
    case "superseded":
      expectKeys(o, ["type"], "$");
      return { type: "superseded" };
    case "left_table":
      expectKeys(o, ["type"], "$");
      return { type: "left_table" };
    case "table_failed":
      expectKeys(o, ["type"], "$");
      return { type: "table_failed" };
    default:
      return fail("$.type", `unknown type "${type}"`);
  }
}

// --- Client message decoding (used by the mock transport and its tests) ---

const COMMAND_NAMES = [
  "start_game",
  "act",
  "showdown_decision",
  "sit_out",
  "sit_back",
  "leave",
  "select_pre_action",
  "clear_pre_action",
] as const satisfies readonly CommandName[];

function decodeActArgs(value: unknown, path: string): ActArgs {
  const o = expectObject(value, ["action", "target"], path);
  const action = expectEnum(o.action, ACTION_NAMES, `${path}.action`);
  if (action === "bet" || action === "raise") {
    return { action, target: expectInt(o.target, `${path}.target`, 1) };
  }
  if (o.target !== null) fail(`${path}.target`, "target must be null for this action");
  return { action, target: null };
}

function decodeCommandPayload(name: string, args: unknown, path: string): CommandPayload {
  switch (name) {
    case "start_game":
      expectObject(args, [], path);
      return { name: "start_game", args: {} };
    case "act":
      return { name: "act", args: decodeActArgs(args, path) };
    case "showdown_decision": {
      const o = expectObject(args, ["decision"], path);
      return {
        name: "showdown_decision",
        args: { decision: expectEnum(o.decision, SHOWDOWN_DECISIONS, `${path}.decision`) },
      };
    }
    case "sit_out":
      expectObject(args, [], path);
      return { name: "sit_out", args: {} };
    case "sit_back":
      expectObject(args, [], path);
      return { name: "sit_back", args: {} };
    case "leave":
      expectObject(args, [], path);
      return { name: "leave", args: {} };
    case "select_pre_action": {
      const o = expectObject(args, ["pre_action"], path);
      return {
        name: "select_pre_action",
        args: { pre_action: decodePreAction(o.pre_action, `${path}.pre_action`) },
      };
    }
    case "clear_pre_action":
      expectObject(args, [], path);
      return { name: "clear_pre_action", args: {} };
    default:
      return fail(path, `unknown command "${name}"`);
  }
}

export function decodeClientMessage(raw: unknown): import("./types").ClientMessage {
  const o = isPlainObject(raw) ? raw : fail("$", "expected an object");
  const type = expectString(o.type, "$.type");
  if (type === "hello") {
    expectKeys(o, ["type", "protocol", "credential"], "$");
    const protocol = expectString(o.protocol, "$.protocol");
    if (protocol !== "go-poker.v1") fail("$.protocol", `unsupported protocol "${protocol}"`);
    return {
      type: "hello",
      protocol: "go-poker.v1",
      credential: expectString(o.credential, "$.credential"),
    };
  }
  if (type === "command") {
    expectKeys(o, ["type", "request_id", "expected_revision", "name", "args"], "$");
    const name = expectString(o.name, "$.name");
    if (!(COMMAND_NAMES as readonly string[]).includes(name))
      fail("$.name", `unknown command "${name}"`);
    const payload = decodeCommandPayload(name, o.args, "$.args");
    return {
      type: "command",
      request_id: expectRequestId(o.request_id, "$.request_id"),
      expected_revision: expectInt(o.expected_revision, "$.expected_revision", 1),
      ...payload,
    } as CommandMessage;
  }
  return fail("$.type", `unknown type "${type}"`);
}

// --- HTTP response decoding ---

export function decodeCreateTableResponse(value: unknown): CreateTableResponseBody {
  const o = expectObject(value, ["table_id", "join_code", "seat", "credential"], "$");
  return {
    table_id: expectString(o.table_id, "$.table_id"),
    join_code: expectString(o.join_code, "$.join_code"),
    seat: expectSeatNumber(o.seat, "$.seat"),
    credential: expectString(o.credential, "$.credential"),
  };
}

export function decodeJoinTableResponse(value: unknown): JoinTableResponseBody {
  const o = expectObject(value, ["table_id", "seat", "credential"], "$");
  return {
    table_id: expectString(o.table_id, "$.table_id"),
    seat: expectSeatNumber(o.seat, "$.seat"),
    credential: expectString(o.credential, "$.credential"),
  };
}

export function decodeHttpErrorBody(value: unknown): HttpErrorBody {
  const o = expectObject(value, ["error"], "$");
  const e = expectObject(o.error, ["code", "message", "field"], "$.error");
  return {
    error: {
      code: expectEnum(e.code, HTTP_ERROR_CODES, "$.error.code"),
      message: expectString(e.message, "$.error.message"),
      field: expectNullOr(e.field, "$.error.field", expectString),
    },
  };
}
