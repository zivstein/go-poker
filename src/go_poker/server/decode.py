"""Strict decoding of inbound client text frames (ADR 0009 §1.3, §5, §6, §12).

The result of decoding is a value: one frozen command, or the error the frame earned. Nothing here touches a table.

- **Shapes only.** The engine alone judges legality (C6.4 Brief §5.9), so a target outside the legal range decodes
  fine and comes back from the engine as `ILLEGAL_ACTION`. A credential's validity is likewise not decided here: an
  unknown and a foreign credential must not be distinguished (ADR 0009 §5), so only its JSON type is checked.
- **Strict** (ADR 0009 §1.3, Brief §5.8): a boolean is not an integer, a float is not an integer, every integer is
  within ±(2⁵³ − 1), and a missing, unknown or extra field is an error.
- **A closed set** (C6.1 E13): the commands are the eight values below, decoded by an exhaustive `match`. There is no
  command registry, no handler table and no dynamic dispatch.
- **Wire strings stay wire strings.** A decoded command carries the protocol's own `"call"` or `"check_or_fold"`;
  turning those into engine values is `mapping`'s job, with its own tables.

The two entry points are `decode_hello` and `decode_command`. Which error code and close code each failure value
becomes is the caller's (the WebSocket's) decision, stated in ADR 0009 §12.
"""

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeGuard

from go_poker.server import dto

# The one protocol identifier this server supports (ADR 0009 §1).
PROTOCOL = "go-poker.v1"

# Every integer on the wire is exactly representable in JavaScript (ADR 0009 §2).
MAX_SAFE_INTEGER = 2**53 - 1

HELLO_KEYS = frozenset({"type", "protocol", "credential"})
ENVELOPE_KEYS = frozenset({"type", "request_id", "expected_revision", "name", "args"})
ACT_KEYS = frozenset({"action", "target"})
SHOWDOWN_DECISION_KEYS = frozenset({"decision"})
SELECT_PRE_ACTION_KEYS = frozenset({"pre_action"})
PRE_ACTION_KEYS = frozenset({"kind", "amount"})
NO_KEYS: frozenset[str] = frozenset()

# ADR 0009 §2: 1-64 characters from [A-Za-z0-9_-], chosen by the client.
REQUEST_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")

# The actions and pre-action kinds that carry an amount; every other value of those enums carries none (ADR 0009 §6).
ACTIONS_WITH_TARGET: frozenset[dto.Action] = frozenset({"bet", "raise"})
PRE_ACTION_KINDS_WITH_AMOUNT: frozenset[dto.PreActionKind] = frozenset({"call_current"})


# --- Handshake values (ADR 0009 §5) ---


@dataclass(frozen=True)
class Hello:
    """A well-formed `hello` for the supported protocol. Whether the credential authenticates is decided elsewhere."""

    protocol: str
    credential: str


@dataclass(frozen=True)
class HelloRequired:
    """The first frame is not a well-formed `hello` (`HELLO_REQUIRED`, close `4400`)."""

    message: str


@dataclass(frozen=True)
class ProtocolMismatch:
    """A well-formed `hello` for another protocol (`PROTOCOL_MISMATCH`, close `4400`)."""

    message: str


type DecodedHello = Hello | HelloRequired | ProtocolMismatch


# --- Command values (ADR 0009 §6) ---


@dataclass(frozen=True)
class StartGame:
    request_id: str
    expected_revision: int


@dataclass(frozen=True)
class Act:
    """A betting action with its wire values: `target` is set exactly for `bet` and `raise`."""

    request_id: str
    expected_revision: int
    action: dto.Action
    target: int | None


@dataclass(frozen=True)
class ShowdownDecision:
    request_id: str
    expected_revision: int
    decision: dto.ShowdownDecision


@dataclass(frozen=True)
class SitOut:
    request_id: str
    expected_revision: int


@dataclass(frozen=True)
class SitBack:
    request_id: str
    expected_revision: int


@dataclass(frozen=True)
class Leave:
    request_id: str
    expected_revision: int


@dataclass(frozen=True)
class SelectPreAction:
    """A pre-action selection with its wire values: `amount` is set exactly for `call_current`."""

    request_id: str
    expected_revision: int
    kind: dto.PreActionKind
    amount: int | None


@dataclass(frozen=True)
class ClearPreAction:
    request_id: str
    expected_revision: int


type Command = StartGame | Act | ShowdownDecision | SitOut | SitBack | Leave | SelectPreAction | ClearPreAction


@dataclass(frozen=True)
class Malformed:
    """The frame could not be interpreted at all (`MALFORMED_MESSAGE`, `request_id` null, the connection stays open).

    It is not a command, so it is no command's outcome.
    """

    message: str


@dataclass(frozen=True)
class InvalidCommand:
    """A `command` with a usable `request_id` and any other defect (`INVALID_COMMAND`, echoed, connection stays open).

    This *is* that command's one outcome (ADR 0009 §8).
    """

    request_id: str
    message: str


type DecodedCommand = Command | Malformed | InvalidCommand


# --- Scalar checks ---


def is_wire_integer(value: object) -> TypeGuard[int]:
    """Whether a decoded JSON value is an integer the protocol accepts (ADR 0009 §2).

    `type(value) is int` rejects `bool`, which is a subclass of `int`, and every float, including `10.0`.
    """
    return type(value) is int and -MAX_SAFE_INTEGER <= value <= MAX_SAFE_INTEGER


def _is_positive_wire_integer(value: object) -> TypeGuard[int]:
    return is_wire_integer(value) and value >= 1


def _keys_problem(fields: Mapping[object, object], expected: frozenset[str], what: str) -> str | None:
    """Why `fields` does not have exactly the expected keys, or None when it does."""
    present = set(fields)
    if present == expected:
        return None
    missing = sorted(expected - present)
    extra = sorted(str(key) for key in present - expected)
    return f"{what} has exactly the fields {sorted(expected)} (missing {missing}, unexpected {extra})"


# --- Hello (ADR 0009 §5) ---


def decode_hello(text: str) -> DecodedHello:
    """Decode a connection's first frame.

    The checks are in the contract's order: a well-formed `hello` first, then the protocol. The credential is only
    required to be a string, because an unknown, a foreign and a misspelled credential must all answer `AUTH_FAILED`.
    """
    try:
        frame = json.loads(text)
    except ValueError:
        return HelloRequired("The first frame is not valid JSON")
    if not isinstance(frame, dict):
        return HelloRequired("The first frame must be a JSON object")
    if (problem := _keys_problem(frame, HELLO_KEYS, "hello")) is not None:
        return HelloRequired(problem)
    if frame["type"] != "hello":
        return HelloRequired("The first frame must be a hello")
    protocol = frame["protocol"]
    credential = frame["credential"]
    if not isinstance(protocol, str) or not isinstance(credential, str):
        return HelloRequired("A hello needs a string protocol and a string credential")
    if protocol != PROTOCOL:
        return ProtocolMismatch(f"Unsupported protocol {protocol!r}; this server supports {PROTOCOL}")
    return Hello(protocol=protocol, credential=credential)


# --- Commands (ADR 0009 §6, §12) ---


def decode_command(text: str) -> DecodedCommand:
    """Decode a text frame of an authenticated connection.

    The order of the checks is what decides which error a frame earns: everything up to and including the
    `request_id` is `Malformed` with no `request_id`, and every later defect is `InvalidCommand` with it echoed.
    """
    try:
        frame = json.loads(text)
    except ValueError:
        return Malformed("The frame is not valid JSON")
    if not isinstance(frame, dict):
        return Malformed("A frame must be a JSON object")

    kind = frame.get("type")
    if kind == "hello":
        return Malformed("hello is accepted only as the first frame")
    if kind != "command":
        return Malformed(f"Unknown message type {kind!r}")

    request_id = frame.get("request_id")
    if not isinstance(request_id, str) or REQUEST_ID.fullmatch(request_id) is None:
        return Malformed("A command needs a request_id of 1-64 characters from [A-Za-z0-9_-]")

    if (problem := _keys_problem(frame, ENVELOPE_KEYS, "A command")) is not None:
        return InvalidCommand(request_id, problem)
    expected_revision = frame["expected_revision"]
    if not _is_positive_wire_integer(expected_revision):
        return InvalidCommand(request_id, "expected_revision must be an integer of at least 1")
    args = frame["args"]
    if not isinstance(args, dict):
        return InvalidCommand(request_id, "args must be a JSON object")

    match frame["name"]:
        case "start_game":
            if (bad := _argless(request_id, args, "start_game")) is not None:
                return bad
            return StartGame(request_id=request_id, expected_revision=expected_revision)
        case "act":
            return _act(request_id, expected_revision, args)
        case "showdown_decision":
            return _showdown_decision(request_id, expected_revision, args)
        case "sit_out":
            if (bad := _argless(request_id, args, "sit_out")) is not None:
                return bad
            return SitOut(request_id=request_id, expected_revision=expected_revision)
        case "sit_back":
            if (bad := _argless(request_id, args, "sit_back")) is not None:
                return bad
            return SitBack(request_id=request_id, expected_revision=expected_revision)
        case "leave":
            if (bad := _argless(request_id, args, "leave")) is not None:
                return bad
            return Leave(request_id=request_id, expected_revision=expected_revision)
        case "select_pre_action":
            return _select_pre_action(request_id, expected_revision, args)
        case "clear_pre_action":
            if (bad := _argless(request_id, args, "clear_pre_action")) is not None:
                return bad
            return ClearPreAction(request_id=request_id, expected_revision=expected_revision)
        case unknown:
            return InvalidCommand(request_id, f"Unknown command name {unknown!r}")


def _argless(request_id: str, args: Mapping[object, object], name: str) -> InvalidCommand | None:
    """The check the five commands whose `args` are exactly `{}` share, or None when the args are empty."""
    problem = _keys_problem(args, NO_KEYS, f"The args of {name}")
    return None if problem is None else InvalidCommand(request_id, problem)


def _act(request_id: str, expected_revision: int, args: Mapping[object, object]) -> Act | InvalidCommand:
    if (problem := _keys_problem(args, ACT_KEYS, "The args of act")) is not None:
        return InvalidCommand(request_id, problem)
    target = args["target"]
    match args["action"]:
        case "fold":
            return _act_value(request_id, expected_revision, "fold", target)
        case "check":
            return _act_value(request_id, expected_revision, "check", target)
        case "call":
            return _act_value(request_id, expected_revision, "call", target)
        case "bet":
            return _act_value(request_id, expected_revision, "bet", target)
        case "raise":
            return _act_value(request_id, expected_revision, "raise", target)
        case unknown:
            return InvalidCommand(request_id, f"Unknown action {unknown!r}")


def _act_value(request_id: str, expected_revision: int, action: dto.Action, target: object) -> Act | InvalidCommand:
    """The one place the target rule is decided: a target exactly for `bet` and `raise` (ADR 0009 §6)."""
    if action in ACTIONS_WITH_TARGET:
        if not _is_positive_wire_integer(target):
            return InvalidCommand(request_id, f"The target of {action} must be an integer of at least 1")
        return Act(request_id=request_id, expected_revision=expected_revision, action=action, target=target)
    if target is not None:
        return InvalidCommand(request_id, f"{action} carries no target, so its target must be null")
    return Act(request_id=request_id, expected_revision=expected_revision, action=action, target=None)


def _showdown_decision(
    request_id: str, expected_revision: int, args: Mapping[object, object]
) -> ShowdownDecision | InvalidCommand:
    if (problem := _keys_problem(args, SHOWDOWN_DECISION_KEYS, "The args of showdown_decision")) is not None:
        return InvalidCommand(request_id, problem)
    match args["decision"]:
        case "show":
            return ShowdownDecision(request_id=request_id, expected_revision=expected_revision, decision="show")
        case "muck":
            return ShowdownDecision(request_id=request_id, expected_revision=expected_revision, decision="muck")
        case unknown:
            return InvalidCommand(request_id, f"Unknown showdown decision {unknown!r}")


def _select_pre_action(
    request_id: str, expected_revision: int, args: Mapping[object, object]
) -> SelectPreAction | InvalidCommand:
    if (problem := _keys_problem(args, SELECT_PRE_ACTION_KEYS, "The args of select_pre_action")) is not None:
        return InvalidCommand(request_id, problem)
    pre_action = args["pre_action"]
    if not isinstance(pre_action, dict):
        return InvalidCommand(request_id, "pre_action must be a JSON object")
    if (problem := _keys_problem(pre_action, PRE_ACTION_KEYS, "A pre_action")) is not None:
        return InvalidCommand(request_id, problem)
    amount = pre_action["amount"]
    match pre_action["kind"]:
        case "check":
            return _pre_action_value(request_id, expected_revision, "check", amount)
        case "check_or_fold":
            return _pre_action_value(request_id, expected_revision, "check_or_fold", amount)
        case "fold":
            return _pre_action_value(request_id, expected_revision, "fold", amount)
        case "call_current":
            return _pre_action_value(request_id, expected_revision, "call_current", amount)
        case unknown:
            return InvalidCommand(request_id, f"Unknown pre-action kind {unknown!r}")


def _pre_action_value(
    request_id: str, expected_revision: int, kind: dto.PreActionKind, amount: object
) -> SelectPreAction | InvalidCommand:
    """The one place the amount rule is decided: an amount exactly for `call_current` (ADR 0009 §6)."""
    if kind in PRE_ACTION_KINDS_WITH_AMOUNT:
        if not _is_positive_wire_integer(amount):
            return InvalidCommand(request_id, f"The amount of a {kind} pre-action must be an integer of at least 1")
        return SelectPreAction(request_id=request_id, expected_revision=expected_revision, kind=kind, amount=amount)
    if amount is not None:
        return InvalidCommand(request_id, f"A {kind} pre-action has no amount, so its amount must be null")
    return SelectPreAction(request_id=request_id, expected_revision=expected_revision, kind=kind, amount=None)
