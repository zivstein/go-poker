"""The inbound decoder against the canonical client fixtures (ADR 0009 §5, §6, §12).

Both lists of `invalid/client_to_server.json` are driven from the file itself, and every case must be classified, so a
case added to the fixtures cannot be silently skipped. Only `type`, `code` and `request_id` of the expected error are
normative; the close codes belong to the WebSocket, which is a later step.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from go_poker.app.pre_actions import PreAction, PreActionKind
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.showdown import ShowdownAction
from go_poker.server import decode, mapping

FIXTURE_ROOT = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0009-wire-protocol-v1"
INVALID = json.loads((FIXTURE_ROOT / "invalid" / "client_to_server.json").read_text(encoding="utf-8"))
AFTER_HELLO: list[dict[str, Any]] = INVALID["after_hello"]
FIRST_FRAME: list[dict[str, Any]] = INVALID["first_frame"]
CLIENT_MESSAGES = sorted((FIXTURE_ROOT / "messages" / "client").glob("*.json"))

# The command value each canonical client frame decodes to, and the engine value it names.
EXPECTED_COMMANDS: dict[str, decode.Command] = {
    "command_act.bet.json": decode.Act(request_id="b-03", expected_revision=5, action="bet", target=20),
    "command_act.call.json": decode.Act(request_id="a-03", expected_revision=3, action="call", target=None),
    "command_act.check.json": decode.Act(request_id="b-02", expected_revision=4, action="check", target=None),
    "command_act.fold.json": decode.Act(request_id="c-01", expected_revision=6, action="fold", target=None),
    "command_act.raise.json": decode.Act(request_id="a-04", expected_revision=6, action="raise", target=60),
    "command_act.raise_short_all_in.json": decode.Act(
        request_id="c-30", expected_revision=17, action="raise", target=990
    ),
    "command_clear_pre_action.json": decode.ClearPreAction(request_id="b-02", expected_revision=3),
    "command_leave.json": decode.Leave(request_id="a-02", expected_revision=3),
    "command_select_pre_action.json": decode.SelectPreAction(
        request_id="b-03", expected_revision=3, kind="check_or_fold", amount=None
    ),
    "command_showdown_decision.muck.json": decode.ShowdownDecision(
        request_id="b-08", expected_revision=14, decision="muck"
    ),
    "command_showdown_decision.show.json": decode.ShowdownDecision(
        request_id="a-07", expected_revision=13, decision="show"
    ),
    "command_sit_back.json": decode.SitBack(request_id="b-02", expected_revision=3),
    "command_sit_out.json": decode.SitOut(request_id="b-01", expected_revision=3),
    "command_start_game.json": decode.StartGame(request_id="a-01", expected_revision=1),
}


def _frame_text(case: dict[str, Any]) -> str:
    """The text frame a fixture case sends: `raw` as is, otherwise its `message` serialized."""
    return case["raw"] if "raw" in case else json.dumps(case["message"])


def _as_error(decoded: decode.DecodedCommand) -> tuple[str, str, str | None]:
    """The `type`, `code` and `request_id` the server would answer a decoded failure with (ADR 0009 §12)."""
    match decoded:
        case decode.Malformed():
            return ("error", "MALFORMED_MESSAGE", None)
        case decode.InvalidCommand(request_id=request_id):
            return ("error", "INVALID_COMMAND", request_id)
        case _:
            return pytest.fail(f"the frame decoded as the command {decoded}")


def test_the_fixture_lists_are_where_this_test_expects_them() -> None:
    assert len(AFTER_HELLO) == 24
    assert len(FIRST_FRAME) == 4
    assert len(CLIENT_MESSAGES) == 15


# --- Frames of an authenticated connection ---


@pytest.mark.parametrize("case", AFTER_HELLO, ids=[case["case"] for case in AFTER_HELLO])
def test_an_invalid_frame_earns_the_error_the_fixture_states(case: dict[str, Any]) -> None:
    expected = case["expect"]
    decoded = decode.decode_command(_frame_text(case))
    assert _as_error(decoded) == (expected["type"], expected["code"], expected["request_id"])
    assert decoded.message, "every error carries a diagnostic message"


@pytest.mark.parametrize("path", CLIENT_MESSAGES, ids=lambda path: path.name)
def test_a_canonical_client_frame_decodes_to_its_command_value(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if path.name == "hello.json":
        assert decode.decode_hello(text) == decode.Hello(protocol="go-poker.v1", credential="test-credential-alice")
        return
    assert path.name in EXPECTED_COMMANDS, f"{path.name} has no expected command value in this test"
    assert decode.decode_command(text) == EXPECTED_COMMANDS[path.name]


def test_every_canonical_client_command_has_an_expected_value() -> None:
    names = {path.name for path in CLIENT_MESSAGES} - {"hello.json"}
    assert names == set(EXPECTED_COMMANDS)


def test_every_command_name_of_the_contract_has_a_canonical_frame() -> None:
    """The closed set of §6, each reached by a fixture, so the decoder's `match` is exercised whole."""
    commands = [path for path in CLIENT_MESSAGES if path.name != "hello.json"]
    decoded = [decode.decode_command(path.read_text(encoding="utf-8")) for path in commands]
    assert {type(command) for command in decoded} == {
        decode.StartGame,
        decode.Act,
        decode.ShowdownDecision,
        decode.SitOut,
        decode.SitBack,
        decode.Leave,
        decode.SelectPreAction,
        decode.ClearPreAction,
    }


# --- The first frame ---


@pytest.mark.parametrize("case", FIRST_FRAME, ids=[case["case"] for case in FIRST_FRAME])
def test_a_first_frame_earns_the_handshake_error_the_fixture_states(case: dict[str, Any]) -> None:
    code = case["expect"]["code"]
    decoded = decode.decode_hello(_frame_text(case))
    match code:
        case "HELLO_REQUIRED":
            assert isinstance(decoded, decode.HelloRequired)
        case "PROTOCOL_MISMATCH":
            assert isinstance(decoded, decode.ProtocolMismatch)
        case "AUTH_FAILED":
            # A well-formed hello for this protocol. Whether the credential authenticates is not decoded here: an
            # unknown, a foreign and a revoked credential are not distinguished (ADR 0009 §5).
            assert isinstance(decoded, decode.Hello)
        case _:
            pytest.fail(f"the fixture expects {code}, which this test does not classify")
    assert case["expect"]["request_id"] is None


# --- Strictness (ADR 0009 §1.3, §2) ---


@pytest.mark.parametrize(
    ("value", "accepted"),
    [
        (0, True),
        (1, True),
        (-1, True),
        (2**53 - 1, True),
        (-(2**53) + 1, True),
        (2**53, False),
        (-(2**53), False),
        (True, False),
        (False, False),
        (1.0, False),
        ("1", False),
        (None, False),
    ],
)
def test_the_one_integer_check_rejects_booleans_floats_and_unsafe_integers(value: object, accepted: bool) -> None:
    assert decode.is_wire_integer(value) is accepted


def _command(**overrides: Any) -> str:
    frame: dict[str, Any] = {
        "type": "command",
        "request_id": "r-1",
        "expected_revision": 4,
        "name": "act",
        "args": {"action": "call", "target": None},
    }
    frame.update(overrides)
    return json.dumps(frame)


@pytest.mark.parametrize(
    ("case", "text"),
    [
        ("type missing", json.dumps({"request_id": "r-1"})),
        ("type not a string", json.dumps({"type": 7})),
        ("a second hello", json.dumps({"type": "hello", "protocol": "go-poker.v1", "credential": "c"})),
        ("request_id not a string", _command(request_id=7)),
        ("request_id empty", _command(request_id="")),
        ("request_id of 65 characters", _command(request_id="r" * 65)),
        ("an empty frame", json.dumps({})),
    ],
)
def test_a_frame_the_server_cannot_correlate_is_malformed(case: str, text: str) -> None:
    assert isinstance(decode.decode_command(text), decode.Malformed)


@pytest.mark.parametrize(
    ("case", "text"),
    [
        ("expected_revision zero", _command(expected_revision=0)),
        ("expected_revision negative", _command(expected_revision=-1)),
        ("expected_revision boolean", _command(expected_revision=True)),
        ("expected_revision above the safe range", _command(expected_revision=2**53)),
        ("name not a string", _command(name=7)),
        ("args not an object", _command(args=[])),
        ("args null", _command(args=None)),
        ("pre_action not an object", _command(name="select_pre_action", args={"pre_action": "check"})),
        ("pre_action extra field", _command(name="select_pre_action", args={"pre_action": {"kind": "check"}})),
        (
            "call_current with a zero amount",
            _command(name="select_pre_action", args={"pre_action": {"kind": "call_current", "amount": 0}}),
        ),
        ("target boolean", _command(args={"action": "bet", "target": True})),
        ("target above the safe range", _command(args={"action": "bet", "target": 2**53})),
    ],
)
def test_a_correlatable_command_with_a_defect_is_an_invalid_command(case: str, text: str) -> None:
    decoded = decode.decode_command(text)
    assert isinstance(decoded, decode.InvalidCommand)
    assert decoded.request_id == "r-1"


@pytest.mark.parametrize(
    ("case", "text"),
    [
        ("request_id of 64 characters", _command(request_id="r" * 64)),
        ("the lowest revision", _command(expected_revision=1)),
        ("the highest safe revision", _command(expected_revision=2**53 - 1)),
    ],
)
def test_a_frame_at_the_edge_of_the_allowed_ranges_decodes(case: str, text: str) -> None:
    assert isinstance(decode.decode_command(text), decode.Act)


def test_an_out_of_range_target_is_the_engines_decision_not_the_decoders() -> None:
    """Brief §5.9: the decoder checks shapes, so a target no stack can pay decodes and comes back ILLEGAL_ACTION."""
    decoded = decode.decode_command(_command(args={"action": "raise", "target": 2**53 - 1}))
    assert decoded == decode.Act(request_id="r-1", expected_revision=4, action="raise", target=2**53 - 1)


@pytest.mark.parametrize(
    ("case", "text"),
    [
        ("not JSON", "{"),
        ("not an object", "[1, 2]"),
        ("a bare string", '"hello"'),
        ("extra field", json.dumps({"type": "hello", "protocol": "go-poker.v1", "credential": "c", "seat": 1})),
        ("missing protocol", json.dumps({"type": "hello", "credential": "c"})),
        ("credential not a string", json.dumps({"type": "hello", "protocol": "go-poker.v1", "credential": 7})),
        ("protocol not a string", json.dumps({"type": "hello", "protocol": 1, "credential": "c"})),
    ],
)
def test_a_first_frame_that_is_not_a_well_formed_hello_requires_a_hello(case: str, text: str) -> None:
    assert isinstance(decode.decode_hello(text), decode.HelloRequired)


def test_a_credential_of_any_shape_is_left_to_authentication() -> None:
    """Only the JSON type is checked here, so an unknown and a malformed credential both answer AUTH_FAILED."""
    text = json.dumps({"type": "hello", "protocol": "go-poker.v1", "credential": "not a credential!"})
    assert decode.decode_hello(text) == decode.Hello(protocol="go-poker.v1", credential="not a credential!")


# --- Decoded commands to engine values (the tables live in `mapping`) ---


@pytest.mark.parametrize(
    ("action", "target", "expected"),
    [
        ("fold", None, Action(ActionType.FOLD)),
        ("check", None, Action(ActionType.CHECK)),
        ("call", None, Action(ActionType.CALL)),
        ("bet", 20, Action(ActionType.BET, 20)),
        ("raise", 60, Action(ActionType.RAISE, 60)),
    ],
)
def test_a_decoded_act_names_an_engine_action(action: Any, target: int | None, expected: Action) -> None:
    assert mapping.betting_action(action, target) == expected


def test_a_decoded_showdown_decision_names_an_engine_showdown_action() -> None:
    assert mapping.showdown_decision("show") is ShowdownAction.SHOW
    assert mapping.showdown_decision("muck") is ShowdownAction.MUCK


@pytest.mark.parametrize(
    ("kind", "amount", "expected"),
    [
        ("check", None, PreAction(PreActionKind.CHECK)),
        ("check_or_fold", None, PreAction(PreActionKind.CHECK_OR_FOLD)),
        ("fold", None, PreAction(PreActionKind.FOLD)),
        ("call_current", 25, PreAction(PreActionKind.CALL_CURRENT, 25)),
    ],
)
def test_a_decoded_pre_action_names_an_engine_pre_action(kind: Any, amount: int | None, expected: PreAction) -> None:
    assert mapping.selected_pre_action(kind, amount) == expected


def test_the_canonical_pre_action_frame_becomes_the_engine_pre_action_it_names() -> None:
    frame = (FIXTURE_ROOT / "messages" / "client" / "command_select_pre_action.json").read_text(encoding="utf-8")
    decoded = decode.decode_command(frame)
    assert isinstance(decoded, decode.SelectPreAction)
    assert mapping.selected_pre_action(decoded.kind, decoded.amount) == PreAction(PreActionKind.CHECK_OR_FOLD)


# --- Boundaries the canonical cases do not reach ---


@pytest.mark.parametrize(
    ("case", "text"),
    [
        ("args null", _command(name="sit_out", args=None)),
        ("pre_action null", _command(name="select_pre_action", args={"pre_action": None})),
        ("pre_action a list", _command(name="select_pre_action", args={"pre_action": [{"kind": "check"}]})),
        (
            "an extra field nested inside pre_action",
            _command(
                name="select_pre_action",
                args={"pre_action": {"kind": "check", "amount": None, "urgent": True}},
            ),
        ),
        (
            "a pre_action kind that is not a string",
            _command(name="select_pre_action", args={"pre_action": {"kind": 7, "amount": None}}),
        ),
        (
            "call_current with a float amount",
            _command(name="select_pre_action", args={"pre_action": {"kind": "call_current", "amount": 25.0}}),
        ),
        (
            "call_current with a boolean amount",
            _command(name="select_pre_action", args={"pre_action": {"kind": "call_current", "amount": True}}),
        ),
        (
            "call_current above the safe range",
            _command(name="select_pre_action", args={"pre_action": {"kind": "call_current", "amount": 2**53}}),
        ),
        ("an action that is not a string", _command(args={"action": 7, "target": None})),
        ("a decision that is not a string", _command(name="showdown_decision", args={"decision": 7})),
        ("a name that is an object", _command(name={"act": True})),
        ("expected_revision null", _command(expected_revision=None)),
        ("expected_revision a string of digits", _command(expected_revision="4")),
        ("expected_revision below the safe range", _command(expected_revision=-(2**53))),
    ],
)
def test_a_further_defect_of_a_correlatable_command_is_an_invalid_command(case: str, text: str) -> None:
    decoded = decode.decode_command(text)
    assert isinstance(decoded, decode.InvalidCommand), decoded
    assert decoded.request_id == "r-1"


@pytest.mark.parametrize(
    ("case", "text"),
    [
        ("a request_id of one character", _command(request_id="a")),
        ("every allowed request_id character", _command(request_id="aZ09_-")),
        ("a target of exactly the highest safe integer", _command(args={"action": "bet", "target": 2**53 - 1})),
        ("a target of one", _command(args={"action": "bet", "target": 1})),
        (
            "call_current with an amount of one",
            _command(name="select_pre_action", args={"pre_action": {"kind": "call_current", "amount": 1}}),
        ),
    ],
)
def test_a_frame_at_another_edge_of_the_allowed_ranges_decodes(case: str, text: str) -> None:
    decoded = decode.decode_command(text)
    assert not isinstance(decoded, (decode.Malformed, decode.InvalidCommand)), decoded


@pytest.mark.parametrize(
    ("case", "character"),
    [("a space", " "), ("a dot", "."), ("a slash", "/"), ("a plus", "+"), ("a newline", "\n"), ("an emoji", "\u2728")],
)
def test_a_request_id_outside_the_contracts_alphabet_is_malformed(case: str, character: str) -> None:
    """ADR 0009 §2: 1-64 characters from [A-Za-z0-9_-], and the match is on the whole value, not a prefix."""
    assert isinstance(decode.decode_command(_command(request_id=f"r{character}1")), decode.Malformed)


def test_a_duplicate_json_key_is_resolved_once_and_deterministically() -> None:
    """v1 does not state what a duplicate key means. Both sides' parsers keep the last value (`json.loads` and
    `JSON.parse` agree), so the decoder must simply be deterministic and must not let the second spelling smuggle a
    frame past a later check."""
    smuggled = '{"type":"command","request_id":"r-1","expected_revision":1,"name":"sit_out","args":{},"args":{"x":1}}'
    decoded = decode.decode_command(smuggled)
    assert isinstance(decoded, decode.InvalidCommand), decoded
    assert decoded.request_id == "r-1"

    repeated_id = (
        '{"type":"command","request_id":"r-1","request_id":"r-2","expected_revision":1,"name":"sit_out","args":{}}'
    )
    assert decode.decode_command(repeated_id) == decode.SitOut(request_id="r-2", expected_revision=1)


def test_a_hello_with_a_duplicate_key_is_decoded_once() -> None:
    text = '{"type":"hello","protocol":"go-poker.v1","credential":"first","credential":"second"}'
    assert decode.decode_hello(text) == decode.Hello(protocol="go-poker.v1", credential="second")


@pytest.mark.parametrize(
    ("case", "text"),
    [
        ("a null frame", "null"),
        ("a number", "7"),
        ("a boolean", "true"),
        ("an empty text frame", ""),
        ("only whitespace", "   "),
        ("trailing content after the object", '{"type": "command"} {}'),
    ],
)
def test_a_frame_that_is_not_one_json_object_is_malformed(case: str, text: str) -> None:
    assert isinstance(decode.decode_command(text), decode.Malformed)
    assert isinstance(decode.decode_hello(text), decode.HelloRequired)


def test_a_hello_whose_type_is_not_hello_requires_a_hello() -> None:
    """The three keys are right but the discriminator is not: still `HELLO_REQUIRED` (ADR 0009 §5)."""
    text = json.dumps({"type": "command", "protocol": "go-poker.v1", "credential": "c"})
    assert isinstance(decode.decode_hello(text), decode.HelloRequired)


def test_an_empty_credential_is_left_to_authentication() -> None:
    """Only the JSON type is checked, so an empty credential is a well-formed hello that cannot authenticate."""
    text = json.dumps({"type": "hello", "protocol": "go-poker.v1", "credential": ""})
    assert decode.decode_hello(text) == decode.Hello(protocol="go-poker.v1", credential="")


@pytest.mark.parametrize(
    ("case", "protocol"),
    [
        ("another version", "go-poker.v2"),
        ("a prefix", "go-poker"),
        ("a different case", "GO-POKER.V1"),
        ("surrounding whitespace", " go-poker.v1 "),
        ("an empty identifier", ""),
    ],
)
def test_only_the_exact_protocol_identifier_is_supported(case: str, protocol: str) -> None:
    """ADR 0009 §1.2: a v1 server supports exactly `["go-poker.v1"]`, and anything else is PROTOCOL_MISMATCH."""
    text = json.dumps({"type": "hello", "protocol": protocol, "credential": "c"})
    assert isinstance(decode.decode_hello(text), decode.ProtocolMismatch)
