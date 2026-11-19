"""`scripts/dev_bot.py`, the local development bot.

Three layers:

- `Brain`, the bot's protocol state machine, is tested without I/O against the canonical ADR 0009 snapshots;
- `run_bot` is tested against a scripted WebSocket server on localhost, for the hello frame, dropped connections,
  uncertain outcomes and terminal close codes;
- the smoke test runs the real server and two real bots through whole hands.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from websockets.asyncio.server import ServerConnection, serve

FIXTURES = Path(__file__).resolve().parents[2] / "docs" / "adr" / "0009-wire-protocol-v1" / "messages"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dev_bot.py"
CREDENTIAL = "secret-credential-of-the-bot"


@pytest.fixture
def bot(script: Callable[[str], ModuleType]) -> ModuleType:
    return script("dev_bot")


def fixture(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / name).read_text())


def snapshot(name: str, **changes: Any) -> str:
    return json.dumps({**fixture(f"server/{name}.json"), **changes})


def counter() -> Callable[[], str]:
    numbers = iter(range(1, 1000))
    return lambda: f"r-{next(numbers)}"


def make_brain(bot: ModuleType, **options: Any) -> tuple[Any, list[str]]:
    logs: list[str] = []
    return bot.Brain(new_request_id=counter(), log=logs.append, **options), logs


def decoded(frame: str | None) -> dict[str, Any]:
    assert frame is not None
    return json.loads(frame)


def view_with(legal: Mapping[str, Any] | None = None, showdown: list[str] | None = None) -> dict[str, Any]:
    return {"hand": {"legal_actions": legal, "showdown_actions": showdown}}


def legal(*offered: str) -> dict[str, bool]:
    return {f"can_{name}": name in offered for name in ("fold", "check", "call", "bet", "raise")}


# --- the decision ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("offered", "expected"),
    [
        (("fold", "check", "bet"), "check"),
        (("fold", "check", "call"), "check"),
        (("fold", "call", "raise"), "call"),
        (("fold", "call"), "call"),
        (("fold",), "fold"),
    ],
)
def test_the_bot_prefers_check_then_call_then_fold(bot: ModuleType, offered: tuple[str, ...], expected: str) -> None:
    assert bot.choose_command(view_with(legal(*offered))) == ("act", {"action": expected, "target": None})


def test_the_bot_never_bets_or_raises_even_when_that_is_all_it_is_offered(bot: ModuleType) -> None:
    assert bot.choose_command(view_with(legal("bet"))) is None
    assert bot.choose_command(view_with(legal("raise"))) is None


def test_the_bot_shows_when_show_is_available_and_mucks_only_as_the_fallback(bot: ModuleType) -> None:
    assert bot.choose_command(view_with(showdown=["show", "muck"])) == ("showdown_decision", {"decision": "show"})
    assert bot.choose_command(view_with(showdown=["muck"])) == ("showdown_decision", {"decision": "muck"})
    assert bot.choose_command(view_with(showdown=[])) is None


@pytest.mark.parametrize("view", [{}, {"hand": None}, view_with(), {"hand": "not a hand"}])
def test_the_bot_does_nothing_when_the_server_offers_it_no_action(bot: ModuleType, view: dict[str, Any]) -> None:
    assert bot.choose_command(view) is None


def test_the_decision_never_depends_on_any_card(bot: ModuleType) -> None:
    base = fixture("server/snapshot.heads_up.preflop.actor.json")["view"]
    peeking = json.loads(json.dumps(base))
    for participant in peeking["hand"]["participants"]:
        participant["hole_cards"] = ["As", "Ad"]
        participant["strength"] = None
    peeking["hand"]["board"] = ["2c", "7d", "9h"]

    assert bot.choose_command(peeking) == bot.choose_command(base) == ("act", {"action": "call", "target": None})


def test_the_bot_source_never_names_a_hole_card() -> None:
    assert "hole_cards" not in SCRIPT.read_text()


# --- the protocol state machine -------------------------------------------------------------------------------------


def test_it_answers_an_actors_snapshot_with_a_correlated_command_at_that_revision(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)

    frame = decoded(brain.receive(snapshot("snapshot.heads_up.preflop.actor")))

    assert frame == {
        "type": "command",
        "request_id": "r-1",
        "expected_revision": 3,
        "name": "act",
        "args": {"action": "call", "target": None},
    }


def test_the_command_has_the_shape_of_the_canonical_client_frame(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)
    canonical = fixture("client/command_act.check.json")
    view = view_with(legal("check", "fold"))
    message = json.dumps(
        {"type": "snapshot", "revision": canonical["expected_revision"], "cause": "command", "view": view}
    )

    assert decoded(brain.receive(message)) == {**canonical, "request_id": "r-1"}


def test_it_does_not_act_in_a_snapshot_where_it_is_not_the_actor(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)

    assert brain.receive(snapshot("snapshot.heads_up.preflop.waiting")) is None
    assert brain.receive(snapshot("snapshot.connected.not_started")) is None


def test_it_shows_in_a_showdown_decision_snapshot(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)

    frame = decoded(brain.receive(snapshot("snapshot.heads_up.showdown_decision")))

    assert (frame["name"], frame["args"], frame["expected_revision"]) == ("showdown_decision", {"decision": "show"}, 14)


def test_it_keeps_one_command_in_flight_and_decides_again_only_on_newer_state(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)
    assert brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=3)) is not None

    # Newer state with an action on offer, but the first command has no outcome yet.
    assert brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=4)) is None
    assert brain.in_flight

    # The outcome arrives: the bot may now act on the newest state, with a new request id and that revision.
    follow_up = decoded(brain.receive(json.dumps({"type": "accepted", "request_id": "r-1", "revision": 4})))
    assert (follow_up["request_id"], follow_up["expected_revision"]) == ("r-2", 4)


def test_it_never_sends_a_second_command_for_the_same_revision(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)
    assert brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=3)) is not None

    rejected = {"type": "rejected", "request_id": "r-1", "code": "ILLEGAL_ACTION", "message": "no"}
    assert brain.receive(json.dumps(rejected)) is None
    # A private snapshot repeats the revision; a duplicate accepted for an old request id is ignored.
    assert brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=3, cause="private")) is None
    assert brain.receive(json.dumps({"type": "accepted", "request_id": "r-1", "revision": 3})) is None
    assert brain.problems == ["ILLEGAL_ACTION"]

    again = decoded(brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=4)))
    assert (again["request_id"], again["expected_revision"]) == ("r-2", 4)


def test_after_a_stale_rejection_it_decides_from_the_newer_snapshot_it_already_has(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)
    brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=3))
    # ADR 0009 §9.4: the newer snapshot arrives before the stale rejection.
    assert brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=5)) is None

    stale = {"type": "rejected", "request_id": "r-1", "code": "STALE_REVISION", "message": "moved"}
    retry = decoded(brain.receive(json.dumps(stale)))

    assert (retry["request_id"], retry["expected_revision"]) == ("r-2", 5)


def test_an_older_snapshot_is_ignored(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)
    brain.receive(snapshot("snapshot.heads_up.preflop.waiting", revision=8))

    assert brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=3)) is None
    assert brain.revision == 8


def test_an_unanswered_command_is_never_sent_again_on_a_new_connection(bot: ModuleType) -> None:
    brain, logs = make_brain(bot)
    first = decoded(brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=3)))

    brain.start_connection()  # the connection dropped before any outcome
    assert not brain.in_flight
    assert any("uncertain" in line and first["request_id"] in line for line in logs)

    # The bot decides afresh from the connected snapshot, as a new command with a new request id. The shared revision
    # did not move, which proves the first command had no effect.
    fresh = decoded(brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=3, cause="connected")))
    assert fresh["request_id"] != first["request_id"]
    assert fresh["expected_revision"] == 3


def test_a_command_that_took_effect_before_the_drop_is_not_repeated(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)
    brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=3))

    brain.start_connection()

    # The reconnect shows newer state in which it is not the actor.
    assert brain.receive(snapshot("snapshot.heads_up.preflop.waiting", revision=4, cause="connected")) is None


def test_an_outcome_for_an_unknown_request_is_ignored(bot: ModuleType) -> None:
    brain, logs = make_brain(bot)
    brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=3))

    assert brain.receive(json.dumps({"type": "accepted", "request_id": "someone-else", "revision": 3})) is None
    assert brain.in_flight
    assert any("unknown request" in line for line in logs)


@pytest.mark.parametrize("kind", ["superseded", "left_table", "table_failed"])
def test_a_terminal_message_stops_the_bot_and_sends_nothing(bot: ModuleType, kind: str) -> None:
    brain, _ = make_brain(bot)
    brain.receive(snapshot("snapshot.heads_up.preflop.waiting"))

    assert brain.receive(json.dumps({"type": kind})) is None
    assert brain.terminal == kind.replace("_", " ")
    assert brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=9)) is None


def test_a_connection_level_error_is_terminal(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)

    assert brain.receive(json.dumps(fixture("server/error.auth_failed.json"))) is None
    assert brain.terminal == "server error AUTH_FAILED"


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        '{"no": "type"}',
        '{"type": "mystery"}',
        '{"type": "snapshot", "revision": 3}',
        '{"type": "snapshot", "revision": "3", "view": {}}',
        '{"type": "snapshot", "revision": 0, "view": {}}',
        '{"type": "snapshot", "revision": true, "view": {}}',
    ],
)
def test_a_frame_v1_does_not_allow_is_a_protocol_error(bot: ModuleType, raw: str) -> None:
    brain, _ = make_brain(bot)

    with pytest.raises(bot.ProtocolError):
        brain.receive(raw)


def host_not_started(bot: ModuleType, occupied: int, *, host: bool = True, phase: str = "not_started") -> str:
    seats = [{"seat": number, "occupant": {"stack": 1000} if number <= occupied else None} for number in range(1, 7)]
    view = {"phase": phase, "seats": seats, "hand": None, "you": {"seat": 1, "is_host": host}}
    return json.dumps({"type": "snapshot", "revision": 2, "cause": "command", "view": view})


def test_a_host_bot_starts_the_game_once_two_players_sit_when_asked_to(bot: ModuleType) -> None:
    brain, _ = make_brain(bot, start_game=True)

    assert brain.receive(host_not_started(bot, occupied=1)) is None
    frame = decoded(brain.receive(host_not_started(bot, occupied=2)))

    assert (frame["name"], frame["args"], frame["expected_revision"]) == ("start_game", {}, 2)


@pytest.mark.parametrize(
    ("options", "occupied", "host", "phase"),
    [
        ({}, 2, True, "not_started"),  # not asked to start the game
        ({"start_game": True}, 2, False, "not_started"),  # not the host
        ({"start_game": True}, 2, True, "hand_in_progress"),  # already started
        ({"start_game": True}, 1, True, "not_started"),  # alone
    ],
)
def test_the_bot_otherwise_leaves_starting_the_game_alone(
    bot: ModuleType, options: dict[str, Any], occupied: int, host: bool, phase: str
) -> None:
    brain, _ = make_brain(bot, **options)

    assert brain.receive(host_not_started(bot, occupied, host=host, phase=phase)) is None


def test_settled_hands_are_counted_once_each_and_not_on_a_connected_snapshot(bot: ModuleType) -> None:
    seen: list[Any] = []
    brain, _ = make_brain(bot, on_settled=seen.append)
    settled = fixture("server/snapshot.heads_up.settled.opponent_mucked.json")
    assert settled["view"]["hand"]["settlement"] is not None
    open_hand = fixture("server/snapshot.heads_up.preflop.waiting.json")

    brain.receive(json.dumps({**settled, "cause": "connected", "revision": 20}))  # the baseline, not a new settlement
    assert brain.settled_hands == 0
    brain.receive(json.dumps({**open_hand, "revision": 21}))
    brain.receive(json.dumps({**settled, "revision": 22}))
    brain.receive(json.dumps({**settled, "revision": 22, "cause": "private"}))

    assert brain.settled_hands == 1
    assert len(seen) == 1


# --- joining --------------------------------------------------------------------------------------------------------


def fake_http(bot: ModuleType, monkeypatch: pytest.MonkeyPatch, answers: list[tuple[int, Any]]) -> list[Any]:
    sent: list[Any] = []

    def post(url: str, body: Mapping[str, Any]) -> tuple[int, Any]:
        sent.append((url, dict(body)))
        return answers[len(sent) - 1]

    monkeypatch.setattr(bot, "_post_json", post)
    return sent


def error_body(code: str) -> dict[str, Any]:
    return {"error": {"code": code, "message": "x", "field": None}}


def created(seat: int) -> tuple[int, dict[str, Any]]:
    return 201, {"table_id": "4f9c2a1e", "seat": seat, "credential": CREDENTIAL}


def test_join_takes_the_lowest_free_seat(bot: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    sent = fake_http(bot, monkeypatch, [(409, error_body("SEAT_TAKEN")), (409, error_body("SEAT_TAKEN")), created(3)])

    membership = bot.join_table("http://h", "k7q2xm", "Dev Bot", None, lambda message: None)

    assert [body["seat"] for _, body in sent] == [1, 2, 3]
    assert all(url == "http://h/tables/by-code/K7Q2XM/members" for url, _ in sent)
    assert all(body["display_name"] == "Dev Bot" for _, body in sent)
    assert (membership.table_id, membership.seat, membership.join_code) == ("4f9c2a1e", 3, "K7Q2XM")
    assert CREDENTIAL not in repr(membership)


def test_join_with_a_chosen_seat_asks_for_that_seat_only(bot: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    sent = fake_http(bot, monkeypatch, [(409, error_body("SEAT_TAKEN"))])

    with pytest.raises(bot.JoinError, match="SEAT_TAKEN"):
        bot.join_table("http://h", "K7Q2XM", "Dev Bot", 4, lambda message: None)

    assert [body["seat"] for _, body in sent] == [4]


def test_join_reports_a_full_table(bot: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    fake_http(bot, monkeypatch, [(409, error_body("SEAT_TAKEN"))] * 2 + [(422, error_body("INVALID_SEAT"))])

    with pytest.raises(bot.JoinError, match="no free seat"):
        bot.join_table("http://h", "K7Q2XM", "Dev Bot", None, lambda message: None)


@pytest.mark.parametrize(
    ("status", "code", "hint"),
    [(409, "DISPLAY_NAME_TAKEN", "--name"), (404, "TABLE_NOT_FOUND", ""), (422, "VALIDATION_FAILED", "")],
)
def test_join_stops_at_any_other_definite_error(
    bot: ModuleType, monkeypatch: pytest.MonkeyPatch, status: int, code: str, hint: str
) -> None:
    sent = fake_http(bot, monkeypatch, [(status, error_body(code))])

    with pytest.raises(bot.JoinError, match=code) as raised:
        bot.join_table("http://h", "K7Q2XM", "Dev Bot", None, lambda message: None)

    assert hint in str(raised.value)
    assert len(sent) == 1


def test_a_join_whose_outcome_is_unknown_is_not_repeated(bot: ModuleType, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def unreachable(request: Any, timeout: float) -> Any:
        calls.append(request.full_url)
        raise TimeoutError("timed out")

    monkeypatch.setattr(bot.urllib.request, "urlopen", unreachable)

    with pytest.raises(bot.JoinError, match="not repeated"):
        bot.join_table("http://127.0.0.1:9", "K7Q2XM", "Dev Bot", None, lambda message: None)

    assert len(calls) == 1


@pytest.mark.parametrize("code", ["", "K7Q2X", "K7Q2XM1", "K7Q2X0", "K7Q2XI", "../x/y", "K7Q 2M"])
def test_a_malformed_join_code_never_reaches_the_network(
    bot: ModuleType, monkeypatch: pytest.MonkeyPatch, code: str
) -> None:
    sent = fake_http(bot, monkeypatch, [])

    with pytest.raises(bot.JoinError, match="not a join code"):
        bot.join_table("http://h", code, "Dev Bot", None, lambda message: None)

    assert sent == []


def test_the_websocket_url_follows_the_http_scheme(bot: ModuleType) -> None:
    assert bot.websocket_url("http://127.0.0.1:8000", "t-1") == "ws://127.0.0.1:8000/ws/tables/t-1"
    assert bot.websocket_url("https://example.test", "t-1") == "wss://example.test/ws/tables/t-1"


def test_the_backoff_is_equal_jitter_between_half_and_all_of_a_capped_exponential(bot: ModuleType) -> None:
    assert [bot.backoff_delay(attempt, lambda: 0.0) for attempt in range(7)] == [0.25, 0.5, 1.0, 2.0, 4.0, 4.0, 4.0]
    assert bot.backoff_delay(0, lambda: 1.0) == 0.5
    assert bot.backoff_delay(20, lambda: 1.0) == 8.0


def test_the_cli_rejects_a_seat_outside_the_product_range(bot: ModuleType) -> None:
    parser = bot.build_parser()

    assert parser.parse_args(["join", "K7Q2XM", "--seat", "9"]).seat == 9
    for seat in ("0", "10"):
        with pytest.raises(SystemExit):
            parser.parse_args(["join", "K7Q2XM", "--seat", seat])


# --- the connection loop against a scripted server ------------------------------------------------------------------


class Script:
    """A scripted server: one handler per connection, in order. Records what each connection received."""

    def __init__(self, handlers: list[Callable[[ServerConnection], Awaitable[None]]]) -> None:
        self.handlers = handlers
        self.received: list[list[dict[str, Any]]] = []

    async def __call__(self, connection: ServerConnection) -> None:
        index = len(self.received)
        self.received.append([])
        handler = self.handlers[min(index, len(self.handlers) - 1)]
        await handler(connection)

    async def read(self, connection: ServerConnection) -> dict[str, Any]:
        message = json.loads(await connection.recv())
        self.received[-1].append(message)
        return message


def run_against(
    bot: ModuleType, script: Script, brain: Any, *, outcome_timeout: float = 5.0, stop_after: float = 5.0
) -> tuple[int | None, list[str]]:
    """Run the bot against `script`; returns its exit code (None if still running at `stop_after`) and its log."""
    logs: list[str] = []
    membership = bot.Membership("table-1", 2, CREDENTIAL, "K7Q2XM", "Dev Bot")

    async def scenario() -> int | None:
        async def no_sleep(delay: float) -> None:
            await asyncio.sleep(0)

        async with serve(script, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            task = asyncio.create_task(
                bot.run_bot(
                    membership,
                    f"http://127.0.0.1:{port}",
                    brain,
                    logs.append,
                    outcome_timeout=outcome_timeout,
                    sleep=no_sleep,
                )
            )
            done, _ = await asyncio.wait({task}, timeout=stop_after)
            if not done:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                return None
            return task.result()

    return asyncio.run(scenario()), logs


def test_it_greets_with_hello_and_plays_one_command_per_turn(bot: ModuleType) -> None:
    async def handler(connection: ServerConnection) -> None:
        hello = await script.read(connection)
        assert hello == {"type": "hello", "protocol": "go-poker.v1", "credential": CREDENTIAL}
        await connection.send(snapshot("snapshot.heads_up.preflop.actor", revision=3, cause="connected"))
        command = await script.read(connection)
        await connection.send(json.dumps({"type": "accepted", "request_id": command["request_id"], "revision": 4}))
        await connection.send(json.dumps({"type": "superseded"}))  # ends the run

    script = Script([handler])
    brain, _ = make_brain(bot)

    code, logs = run_against(bot, script, brain)

    assert code == 1
    assert [message["type"] for message in script.received[0]] == ["hello", "command"]
    assert script.received[0][1]["expected_revision"] == 3
    assert not any(CREDENTIAL in line for line in logs)


def test_a_dropped_connection_with_an_unanswered_command_reconnects_and_decides_afresh(bot: ModuleType) -> None:
    async def drop_after_command(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.send(snapshot("snapshot.heads_up.preflop.actor", revision=3, cause="connected"))
        await script.read(connection)  # the command, which is never answered
        await connection.close(1011)

    async def moved_on(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.send(snapshot("snapshot.heads_up.preflop.waiting", revision=4, cause="connected"))
        await asyncio.sleep(0.3)  # no command is expected
        await connection.send(json.dumps({"type": "table_failed"}))

    script = Script([drop_after_command, moved_on])
    brain, logs = make_brain(bot)

    code, _ = run_against(bot, script, brain)

    assert code == 1
    assert [message["type"] for message in script.received[0]] == ["hello", "command"]
    assert [message["type"] for message in script.received[1]] == ["hello"]
    assert any("uncertain" in line for line in logs)


def test_after_a_drop_a_turn_that_is_still_ours_gets_one_new_command_with_a_new_request_id(bot: ModuleType) -> None:
    async def drop(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.send(snapshot("snapshot.heads_up.preflop.actor", revision=3, cause="connected"))
        await script.read(connection)
        await connection.close(1006)

    async def same_state(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.send(snapshot("snapshot.heads_up.preflop.actor", revision=3, cause="connected"))
        await script.read(connection)
        await connection.send(json.dumps({"type": "superseded"}))

    script = Script([drop, same_state])
    brain, _ = make_brain(bot)

    run_against(bot, script, brain)

    first = script.received[0][1]
    second = script.received[1][1]
    assert second["request_id"] != first["request_id"]
    assert second["expected_revision"] == 3
    assert len(script.received[1]) == 2  # hello and exactly one command


def test_a_command_with_no_outcome_in_time_is_treated_as_uncertain_and_the_bot_reconnects(bot: ModuleType) -> None:
    async def silent(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.send(snapshot("snapshot.heads_up.preflop.actor", revision=3, cause="connected"))
        await script.read(connection)
        await connection.wait_closed()

    async def finish(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.send(json.dumps({"type": "table_failed"}))

    script = Script([silent, finish])
    brain, _ = make_brain(bot)

    code, logs = run_against(bot, script, brain, outcome_timeout=0.2)

    assert code == 1
    assert len(script.received) == 2
    assert any("no outcome" in line for line in logs)


@pytest.mark.parametrize("close_code", [4400, 4401, 4409, 4410, 4500])
def test_a_terminal_close_code_ends_the_run_without_reconnecting(bot: ModuleType, close_code: int) -> None:
    async def refuse(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.close(close_code)

    script = Script([refuse])
    brain, _ = make_brain(bot)

    code, _ = run_against(bot, script, brain)

    assert code == 1
    assert len(script.received) == 1


def test_any_other_close_is_reconnected_until_the_run_is_stopped(bot: ModuleType) -> None:
    async def going_away(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.close(1001)

    script = Script([going_away])
    brain, _ = make_brain(bot)

    code, _ = run_against(bot, script, brain, stop_after=0.5)

    assert code is None  # still running when stopped: the bot keeps going until explicitly stopped
    assert len(script.received) > 1


def test_a_binary_frame_is_a_protocol_failure(bot: ModuleType) -> None:
    async def binary(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.send(b"\x00")

    script = Script([binary])
    brain, _ = make_brain(bot)

    code, logs = run_against(bot, script, brain)

    assert code == 1
    assert any("binary" in line for line in logs)


# --- the smoke test -------------------------------------------------------------------------------------------------


def test_smoke_two_bots_play_whole_hands_against_the_real_server(
    bot: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    code = asyncio.run(bot.run_smoke(hands=2, timeout=30.0))

    assert capsys.readouterr().out.strip() == "SMOKE: PASS (2 hands played by two bots)"
    assert code == 0


def test_a_refused_connection_says_the_server_is_not_running(bot: ModuleType) -> None:
    with pytest.raises(bot.JoinError, match="nothing is listening"):
        bot.join_table("http://127.0.0.1:9", "K7Q2XM", "Dev Bot", None, lambda message: None)


def test_the_join_command_has_no_start_game_flag_because_a_joined_bot_is_never_the_host(bot: ModuleType) -> None:
    with pytest.raises(SystemExit):
        bot.build_parser().parse_args(["join", "K7Q2XM", "--start-game"])


# --- graceful shutdown: the Brain -----------------------------------------------------------------------------------


def accepted(request_id: str, revision: int = 3) -> str:
    return json.dumps({"type": "accepted", "request_id": request_id, "revision": revision})


def rejected(request_id: str, code: str) -> str:
    return json.dumps({"type": "rejected", "request_id": request_id, "code": code, "message": "x"})


def test_a_stopping_bot_sends_one_leave_with_a_fresh_request_id_and_the_current_revision(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)
    brain.receive(snapshot("snapshot.heads_up.preflop.waiting", revision=7))

    assert decoded(brain.begin_shutdown()) == {
        "type": "command",
        "request_id": "r-1",
        "expected_revision": 7,
        "name": "leave",
        "args": {},
    }
    assert brain.in_flight
    assert brain.leave_result is None


def test_a_stopping_bot_never_plays_on_even_on_its_own_turn(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)
    brain.receive(snapshot("snapshot.heads_up.preflop.waiting", revision=3))
    brain.begin_shutdown()
    brain.receive(accepted("r-1"))

    assert brain.leave_result == "left"
    assert brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=4)) is None
    assert brain.receive(snapshot("snapshot.heads_up.showdown_decision", revision=5)) is None


def test_the_leave_waits_for_a_command_in_flight_and_is_then_sent_once_at_the_newer_revision(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)
    first = decoded(brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=3)))
    assert first["name"] == "act"

    assert brain.begin_shutdown() is None  # the act has no outcome yet: no second command alongside it
    assert brain.receive(snapshot("snapshot.heads_up.preflop.waiting", revision=4)) is None

    leave = decoded(brain.receive(accepted(first["request_id"], 4)))
    assert (leave["name"], leave["request_id"], leave["expected_revision"]) == ("leave", "r-2", 4)
    # While the Leave is in flight, further snapshots and an old outcome produce nothing.
    assert brain.receive(snapshot("snapshot.heads_up.preflop.waiting", revision=5)) is None
    assert brain.receive(accepted(first["request_id"], 4)) is None


def test_a_rejected_act_does_not_block_the_leave_at_the_same_revision(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)
    first = decoded(brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=3)))
    brain.begin_shutdown()

    leave = decoded(brain.receive(rejected(first["request_id"], "ILLEGAL_ACTION")))

    assert (leave["name"], leave["expected_revision"]) == ("leave", 3)


def test_a_shutdown_before_any_snapshot_sends_the_leave_on_the_first_one(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)

    assert brain.begin_shutdown() is None
    leave = decoded(brain.receive(snapshot("snapshot.connected.not_started", revision=2, cause="connected")))

    assert (leave["name"], leave["expected_revision"]) == ("leave", 2)


def test_a_stale_leave_is_sent_again_only_as_a_new_command_on_newer_state(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)
    brain.receive(snapshot("snapshot.heads_up.preflop.waiting", revision=3))
    brain.begin_shutdown()
    # ADR 0009 §9.4: the newer snapshot arrives first, then the stale rejection.
    assert brain.receive(snapshot("snapshot.heads_up.preflop.waiting", revision=4)) is None

    again = decoded(brain.receive(rejected("r-1", "STALE_REVISION")))

    assert (again["name"], again["request_id"], again["expected_revision"]) == ("leave", "r-2", 4)
    assert brain.leave_result is None
    assert brain.problems == []


def test_a_stale_leave_with_no_newer_state_is_not_sent_again_at_the_same_revision(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)
    brain.receive(snapshot("snapshot.heads_up.preflop.waiting", revision=3))
    brain.begin_shutdown()

    assert brain.receive(rejected("r-1", "STALE_REVISION")) is None  # no snapshot newer than 3 exists


@pytest.mark.parametrize(
    ("code", "result"), [("NO_CHANGE", "already"), ("NOT_A_MEMBER", "already"), ("NOT_HOST", "refused: NOT_HOST")]
)
def test_a_rejected_leave_ends_the_attempt_and_is_never_repeated_at_that_revision(
    bot: ModuleType, code: str, result: str
) -> None:
    brain, _ = make_brain(bot)
    brain.receive(snapshot("snapshot.heads_up.preflop.waiting", revision=3))
    brain.begin_shutdown()

    assert brain.receive(rejected("r-1", code)) is None

    assert brain.leave_result == result
    assert brain.receive(snapshot("snapshot.heads_up.preflop.waiting", revision=9)) is None


def test_left_table_during_a_shutdown_counts_as_left(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)
    brain.receive(snapshot("snapshot.heads_up.preflop.waiting", revision=3))
    brain.begin_shutdown()

    brain.receive(json.dumps({"type": "left_table"}))

    assert brain.leave_result == "left"
    assert brain.terminal == "left table"


def test_no_leave_is_ever_sent_without_a_shutdown_request(bot: ModuleType) -> None:
    brain, _ = make_brain(bot)
    frames = [brain.receive(snapshot("snapshot.heads_up.preflop.actor", revision=3))]
    brain.start_connection()  # a dropped connection
    frames.append(brain.receive(snapshot("snapshot.heads_up.preflop.waiting", revision=3, cause="connected")))
    frames.append(brain.receive(snapshot("snapshot.heads_up.showdown_decision", revision=4)))

    assert "leave" not in [decoded(frame)["name"] for frame in frames if frame is not None]


# --- graceful shutdown: the connection loop -------------------------------------------------------------------------


def run_stopping(
    bot: ModuleType,
    script: Script,
    brain: Any,
    *,
    stop_when: Callable[[Script], bool],
    deadline: float = 3.0,
    outcome_timeout: float = 5.0,
    patience: float = 5.0,
    sleep: Callable[[float], Any] | None = None,
) -> tuple[int | None, list[str], float]:
    """Run the bot against `script`; set its stop event once `stop_when(script)` holds. Returns the exit code (None if
    it did not finish within `patience`), its log, and how long it ran after the stop was requested."""
    logs: list[str] = []
    membership = bot.Membership("table-1", 2, CREDENTIAL, "K7Q2XM", "Dev Bot")

    async def scenario() -> tuple[int | None, float]:
        stop = asyncio.Event()
        async with serve(script, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            task = asyncio.create_task(
                bot.run_bot(
                    membership,
                    f"http://127.0.0.1:{port}",
                    brain,
                    logs.append,
                    outcome_timeout=outcome_timeout,
                    sleep=sleep or asyncio.sleep,
                    stop=stop,
                    shutdown_deadline=deadline,
                )
            )
            loop = asyncio.get_running_loop()
            end = loop.time() + patience
            while not stop_when(script) and loop.time() < end:
                await asyncio.sleep(0.01)
            stop.set()
            requested = loop.time()
            done, _ = await asyncio.wait({task}, timeout=patience)
            elapsed = loop.time() - requested
            if not done:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                return None, elapsed
            return task.result(), elapsed

    code, elapsed = asyncio.run(scenario())
    return code, logs, elapsed


def names(script: Script, connection: int = 0) -> list[str]:
    if connection >= len(script.received):
        return []
    return [message.get("name", message["type"]) for message in script.received[connection]]


def test_stopping_a_connected_bot_sends_one_leave_and_exits_cleanly_when_it_is_accepted(bot: ModuleType) -> None:
    async def handler(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.send(snapshot("snapshot.heads_up.preflop.waiting", revision=3, cause="connected"))
        leave = await script.read(connection)
        await connection.send(accepted(leave["request_id"], 3))
        await connection.wait_closed()

    script = Script([handler])
    brain, _ = make_brain(bot)

    code, logs, elapsed = run_stopping(
        bot, script, brain, stop_when=lambda s: len(s.received) == 1 and brain.revision == 3
    )

    assert code == 0
    assert elapsed < 2
    assert names(script) == ["hello", "leave"]
    assert script.received[0][1]["expected_revision"] == 3
    assert brain.leave_result == "left"
    assert any("left the table" in line for line in logs)
    assert not any(CREDENTIAL in line for line in logs)


def test_stopping_during_the_bots_own_turn_waits_for_its_outcome_and_then_leaves(bot: ModuleType) -> None:
    async def handler(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.send(snapshot("snapshot.heads_up.preflop.actor", revision=3, cause="connected"))
        act = await script.read(connection)
        await asyncio.sleep(0.3)  # the bot is asked to stop while this command is unanswered
        await connection.send(snapshot("snapshot.heads_up.preflop.waiting", revision=4))
        await connection.send(accepted(act["request_id"], 4))
        leave = await script.read(connection)
        await connection.send(accepted(leave["request_id"], 4))

    script = Script([handler])
    brain, _ = make_brain(bot)

    code, _, _ = run_stopping(bot, script, brain, stop_when=lambda s: names(s) == ["hello", "act"])

    assert code == 0
    assert names(script) == ["hello", "act", "leave"]
    assert script.received[0][2]["expected_revision"] == 4
    assert script.received[0][2]["request_id"] != script.received[0][1]["request_id"]


def test_the_shutdown_is_bounded_when_the_leave_is_never_answered_and_the_leave_is_not_repeated(
    bot: ModuleType,
) -> None:
    async def handler(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.send(snapshot("snapshot.heads_up.preflop.waiting", revision=3, cause="connected"))
        await script.read(connection)  # the leave, never answered
        await connection.wait_closed()

    script = Script([handler])
    brain, _ = make_brain(bot)

    code, logs, elapsed = run_stopping(
        bot, script, brain, stop_when=lambda s: brain.revision == 3, deadline=0.4, patience=8.0
    )

    assert code == 0
    assert 0.3 < elapsed < 3
    assert names(script) == ["hello", "leave"]
    assert len(script.received) == 1  # no reconnect
    assert any("not sent again" in line for line in logs)


def test_an_unanswered_command_that_outlasts_the_deadline_is_never_followed_by_a_leave(bot: ModuleType) -> None:
    async def handler(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.send(snapshot("snapshot.heads_up.preflop.actor", revision=3, cause="connected"))
        await script.read(connection)  # the act, never answered
        await connection.wait_closed()

    script = Script([handler])
    brain, _ = make_brain(bot)

    code, _, elapsed = run_stopping(
        bot, script, brain, stop_when=lambda s: names(s) == ["hello", "act"], deadline=0.4, patience=8.0
    )

    assert code == 0
    assert elapsed < 3
    assert names(script) == ["hello", "act"]


def test_a_connection_lost_before_the_leave_is_answered_exits_without_reconnecting_or_resending(
    bot: ModuleType,
) -> None:
    async def handler(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.send(snapshot("snapshot.heads_up.preflop.waiting", revision=3, cause="connected"))
        await script.read(connection)  # the leave
        await connection.close(1011)

    script = Script([handler])
    brain, _ = make_brain(bot)

    code, logs, elapsed = run_stopping(bot, script, brain, stop_when=lambda s: brain.revision == 3)

    assert code == 0
    assert elapsed < 2
    assert len(script.received) == 1
    assert names(script) == ["hello", "leave"]
    assert any("connection lost" in line for line in logs)


def test_stopping_while_waiting_to_reconnect_exits_at_once_and_sends_nothing(bot: ModuleType) -> None:
    async def handler(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.close(1001)

    async def long_sleep(delay: float) -> None:
        await asyncio.sleep(30)

    script = Script([handler])
    brain, _ = make_brain(bot)

    code, logs, elapsed = run_stopping(bot, script, brain, stop_when=lambda s: len(s.received) == 1, sleep=long_sleep)

    assert code == 0
    assert elapsed < 2
    assert len(script.received) == 1
    assert names(script) == ["hello"]
    assert any("nothing to leave" in line for line in logs)


def test_stopping_with_the_server_gone_exits_without_hanging(bot: ModuleType) -> None:
    logs: list[str] = []
    brain, _ = make_brain(bot)
    membership = bot.Membership("table-1", 2, CREDENTIAL, "K7Q2XM", "Dev Bot")

    async def scenario() -> tuple[int, float]:
        stop = asyncio.Event()
        task = asyncio.create_task(bot.run_bot(membership, "http://127.0.0.1:9", brain, logs.append, stop=stop))
        await asyncio.sleep(0.3)  # connection refused, now backing off
        stop.set()
        started = asyncio.get_running_loop().time()
        code = await asyncio.wait_for(task, 3)
        return code, asyncio.get_running_loop().time() - started

    code, elapsed = asyncio.run(scenario())

    assert code == 0
    assert elapsed < 1


def test_a_temporary_disconnection_never_makes_the_bot_send_a_leave(bot: ModuleType) -> None:
    async def drop(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.send(snapshot("snapshot.heads_up.preflop.waiting", revision=3, cause="connected"))
        await connection.close(1011)

    async def steady(connection: ServerConnection) -> None:
        await script.read(connection)
        await connection.send(snapshot("snapshot.heads_up.preflop.waiting", revision=3, cause="connected"))
        await connection.wait_closed()

    script = Script([drop, steady])
    brain, _ = make_brain(bot)

    code, _ = run_against(bot, script, brain, stop_after=0.6)

    assert code is None  # still running: nobody asked it to stop
    assert len(script.received) == 2
    assert all("leave" not in names(script, index) for index in range(2))


# --- graceful shutdown: against the real server ---------------------------------------------------------------------


def test_stopping_a_bot_releases_its_seat_on_the_real_server(
    bot: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    from go_poker.server.config import ServerConfig

    async def scenario() -> tuple[int, list[str], Any]:
        logs: list[str] = []
        config = ServerConfig(next_hand_pause_seconds=0.2)
        async with bot.local_server(config) as base_url:
            host = await asyncio.to_thread(bot.create_table, base_url, "Host")
            guest = await asyncio.to_thread(bot.join_table, base_url, host.join_code, "Guest", 2, logs.append)
            stop = asyncio.Event()

            def guest_log(message: str) -> None:
                logs.append(message)
                if message.startswith("sending act"):
                    stop.set()  # Ctrl+C lands while the guest's first action is unanswered, in the middle of a hand

            host_brain = bot.Brain(start_game=True)
            guest_brain = bot.Brain(log=guest_log)
            host_task = asyncio.create_task(bot.run_bot(host, base_url, host_brain, lambda message: None))
            guest_task = asyncio.create_task(bot.run_bot(guest, base_url, guest_brain, guest_log, stop=stop))
            try:
                async with asyncio.timeout(20):
                    code = await guest_task
                    # The host keeps playing; the seat is released at the end of the hand.
                    while (host_brain.view or {"seats": [{}, {"occupant": 1}]})["seats"][1]["occupant"] is not None:
                        await asyncio.sleep(0.05)
            finally:
                host_task.cancel()
                await asyncio.gather(host_task, return_exceptions=True)
            # The freed seat can be taken again.
            again = await asyncio.to_thread(bot.join_table, base_url, host.join_code, "Newcomer", 2, logs.append)
            return code, logs, (guest_brain.leave_result, again.seat, host_brain.problems)

    code, logs, (result, new_seat, problems) = asyncio.run(scenario())

    assert code == 0
    assert result in ("left", "already")
    assert new_seat == 2
    assert problems == []
    assert any(line.startswith("sending leave") for line in logs)


def test_stopping_a_bot_before_the_game_starts_frees_its_seat_at_once(bot: ModuleType) -> None:
    from go_poker.server.config import ServerConfig

    async def scenario() -> tuple[int, str, int]:
        logs: list[str] = []
        async with bot.local_server(ServerConfig()) as base_url:
            host = await asyncio.to_thread(bot.create_table, base_url, "Host")
            guest = await asyncio.to_thread(bot.join_table, base_url, host.join_code, "Guest", 3, logs.append)
            stop = asyncio.Event()
            brain = bot.Brain()
            task = asyncio.create_task(bot.run_bot(guest, base_url, brain, logs.append, stop=stop))
            async with asyncio.timeout(10):
                while brain.revision is None:
                    await asyncio.sleep(0.02)
            stop.set()
            code = await asyncio.wait_for(task, 10)
            again = await asyncio.to_thread(bot.join_table, base_url, host.join_code, "Newcomer", 3, logs.append)
            return code, brain.leave_result or "", again.seat

    code, result, seat = asyncio.run(scenario())

    assert (code, result, seat) == (0, "left", 3)
