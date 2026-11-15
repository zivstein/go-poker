"""The in-memory table directory and the default application (ADR 0008 §6, ADR 0009 §2, §4).

Join codes are unique among the *active* codes, so a collision is drawn again and a code is released when its table
leaves. Both rules are the directory's own, and neither is reachable through a scenario, because every scenario
injects one fixed code.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from go_poker.app.identity import DisplayName
from go_poker.server import decode
from go_poker.server.app import create_app
from go_poker.server.config import ServerConfig
from go_poker.server.directory import JOIN_CODE_ATTEMPTS, JoinCodeUnavailableError, TableDirectory

START_GAME = decode.StartGame(request_id="a-01", expected_revision=1)


def _config(**overrides: Any) -> ServerConfig:
    return ServerConfig(**overrides)


def test_a_colliding_join_code_is_drawn_again_until_it_is_free() -> None:
    codes = iter(["K7Q2XM", "K7Q2XM", "K7Q2XM", "AAAA22"])
    directory = TableDirectory(_config(new_join_code=lambda: next(codes)))

    first = directory.create(DisplayName("Alice"))
    second = directory.create(DisplayName("Bob"))

    assert (first.runtime.join_code, second.runtime.join_code) == ("K7Q2XM", "AAAA22")
    assert directory.by_code("K7Q2XM") is first.runtime
    assert directory.by_code("AAAA22") is second.runtime
    assert first.runtime.table_id != second.runtime.table_id


def test_a_code_is_matched_case_insensitively_whatever_case_it_was_drawn_in() -> None:
    directory = TableDirectory(_config(new_join_code=lambda: "K7Q2XM"))
    created = directory.create(DisplayName("Alice"))

    for spelling in ("K7Q2XM", "k7q2xm", "K7q2Xm"):
        assert directory.by_code(spelling) is created.runtime
    assert directory.by_code("K7Q2X") is None
    assert directory.by_code("") is None


def test_a_failed_table_releases_its_code_for_a_new_table(monkeypatch: pytest.MonkeyPatch) -> None:
    codes = iter(["K7Q2XM", "K7Q2XM"])
    directory = TableDirectory(_config(new_join_code=lambda: next(codes)))
    created = directory.create(DisplayName("Alice"))

    def defect(*arguments: object, **keywords: object) -> None:
        raise RuntimeError("an injected defect")

    monkeypatch.setattr(created.runtime._session, "start_game", defect)  # noqa: SLF001
    connection = created.runtime.new_connection(created.credential, created.user_id)
    created.runtime.connect(connection)
    created.runtime.execute(START_GAME, connection)

    assert created.runtime.failed is True
    assert directory.by_code("K7Q2XM") is None
    assert directory.get(created.runtime.table_id) is None

    reused = directory.create(DisplayName("Carol"))

    assert reused.runtime.join_code == "K7Q2XM"
    assert directory.by_code("K7Q2XM") is reused.runtime


def test_the_directory_lists_its_tables_in_creation_order() -> None:
    codes = iter(["K7Q2XM", "AAAA22", "BBBB33"])
    directory = TableDirectory(_config(new_join_code=lambda: next(codes)))

    created = [directory.create(DisplayName(name)) for name in ("Alice", "Bob", "Carol")]

    assert directory.table_ids == tuple(each.runtime.table_id for each in created)
    assert len(set(directory.table_ids)) == 3


def test_an_exhausted_code_space_fails_loudly_instead_of_hanging() -> None:
    """`JOIN_CODE_ATTEMPTS` draws and no free code is a server defect, not a silent retry loop."""
    draws = 0

    def constant() -> str:
        nonlocal draws
        draws += 1
        return "K7Q2XM"

    directory = TableDirectory(_config(new_join_code=constant))
    directory.create(DisplayName("Alice"))
    before = draws

    with pytest.raises(JoinCodeUnavailableError):
        directory.create(DisplayName("Bob"))

    assert draws - before == JOIN_CODE_ATTEMPTS, "the bound is on the draws, not on the tables"
    assert directory.table_ids == (directory.table_ids[0],), "the failed create added no table"


def test_a_credential_authenticates_only_at_its_own_table() -> None:
    codes = iter(["K7Q2XM", "AAAA22"])
    directory = TableDirectory(_config(new_join_code=lambda: next(codes)))

    first = directory.create(DisplayName("Alice"))
    second = directory.create(DisplayName("Bob"))

    assert first.runtime.authenticate(first.credential) == first.user_id
    assert first.runtime.authenticate(second.credential) is None
    assert second.runtime.authenticate(first.credential) is None
    assert first.credential != second.credential
    assert first.user_id != second.user_id


# --- The default application (C6.4 Brief §2.1) ---


def test_the_default_application_runs_with_the_production_generators() -> None:
    """`create_app()` takes no configuration, so this exercises the real id, code and credential generators."""
    with TestClient(create_app()) as client:
        created = client.post("/tables", json={"display_name": "Alice"})
        assert created.status_code == 201
        body = created.json()
        assert len(body["join_code"]) == 6
        assert len(body["credential"]) == 43
        assert body["table_id"] != body["credential"]

        joined = client.post(f"/tables/by-code/{body['join_code']}/members", json={"display_name": "Bob", "seat": 2})
        assert joined.status_code == 201
        assert joined.json()["credential"] != body["credential"]

        second = client.post("/tables", json={"display_name": "Carol"})
        assert second.json()["join_code"] != body["join_code"], "two tables never share an active code"
        assert second.json()["table_id"] != body["table_id"]
