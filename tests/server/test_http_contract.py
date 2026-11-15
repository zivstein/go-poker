"""The HTTP surface at its boundaries (ADR 0009 §4).

The create and join bodies, the display-name and seat rules, the four error codes a join can earn, the order of the
checks, and `Cache-Control: no-store` on an error response and not only on a 2xx. Everything here drives the real
application: the rules themselves belong to `DisplayName` and `TableSession`, and these tests prove the HTTP surface
reaches them and renders their answer as the contract's error body.

The boundaries are the ones a defect hides at: 20 and 21 characters, a name that trims to nothing, a decomposed name
that collides with a composed one, seat 0, 9 and 10 against the product range, and a seat above *this* table's
`max_seats`, which is a different code from a seat outside 1-9.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from go_poker.app.results import Rejected, RejectionCode

JOIN_CODE = "K7Q2XM"
TABLE_ID = "4f9c2a1e-8d3b-4c5a-9e7f-1a2b3c4d5e6f"

# A composed and a decomposed spelling of the same name: NFC normalization must make them the same name, and
# `conflict_key` must make either collide with the other case-insensitively (ADR 0009 §4).
COMPOSED = "Zo\u00eb"  # Zoë, with a composed e-diaeresis
DECOMPOSED = "Zoe\u0308"  # the same name, with a combining diaeresis
# Unicode category C characters: a zero-width space and a right-to-left override.
ZERO_WIDTH = "Al\u200bice"  # a zero-width space (category Cf)
BIDI_OVERRIDE = "Al\u202eice"  # a right-to-left override (category Cf)


@dataclass
class Http:
    """One real application with one table already created, whose host is `COMPOSED` at seat 1."""

    client: TestClient
    harness: Any

    @property
    def members(self) -> str:
        return f"/tables/by-code/{JOIN_CODE}/members"

    def join(self, **body: Any) -> Any:
        return self.client.post(self.members, json=body)

    def error(self, response: Any) -> tuple[int, str | None, str | None]:
        """The status, wire code and field of an error response, which is all that is normative."""
        assert response.headers["cache-control"] == "no-store", "every response carries no-store (ADR 0009 §4)"
        body = response.json()
        assert set(body) == {"error"}, body
        assert set(body["error"]) == {"code", "message", "field"}, body
        assert body["error"]["message"], "an error carries a diagnostic message"
        return response.status_code, body["error"]["code"], body["error"]["field"]


def _codes() -> Callable[[], str]:
    """The table under test gets the contract's code; a second table of the same test gets a different one, because
    the directory draws again until a code is free."""
    issued = iter([JOIN_CODE, "AAAA22", "BBBB33", "CCCC44"])
    return lambda: next(issued)


@pytest.fixture
def http(make_app: Callable[..., Any]) -> Iterator[Http]:
    harness = make_app(new_table_id=lambda: TABLE_ID, new_join_code=_codes())
    with TestClient(harness.app) as client:
        created = client.post("/tables", json={"display_name": COMPOSED})
        assert created.status_code == 201, created.json()
        harness.credentials.append(created.json()["credential"])
        yield Http(client=client, harness=harness)


# --- The display name (ADR 0009 §4 Field rules) ---


def test_a_name_of_twenty_characters_is_accepted_and_one_of_twenty_one_is_not(http: Http) -> None:
    assert http.join(display_name="D" * 20, seat=2).status_code == 201
    assert http.error(http.join(display_name="E" * 21, seat=3)) == (422, "VALIDATION_FAILED", "display_name")


@pytest.mark.parametrize(
    ("case", "display_name"),
    [
        ("empty", ""),
        ("only spaces", "   "),
        ("only a tab", "\t"),
        ("a zero-width space", ZERO_WIDTH),
        ("a bidi override", BIDI_OVERRIDE),
        ("twenty-one characters", "F" * 21),
        ("twenty-one characters after trimming", "  " + "F" * 21 + "  "),
    ],
)
def test_a_name_the_contract_forbids_is_a_validation_failure(http: Http, case: str, display_name: str) -> None:
    assert http.error(http.join(display_name=display_name, seat=2)) == (422, "VALIDATION_FAILED", "display_name")
    assert http.error(http.client.post("/tables", json={"display_name": display_name})) == (
        422,
        "VALIDATION_FAILED",
        "display_name",
    )


def test_a_name_is_trimmed_and_normalized_before_it_is_seated(http: Http) -> None:
    """The seated name is the trimmed, NFC-normalized one, so the table shows it and compares it that way."""
    joined = http.join(display_name=f"  {DECOMPOSED}x  ", seat=2)
    assert joined.status_code == 201
    occupants = _occupant_names(http)
    assert occupants[2] == f"{COMPOSED}x", occupants


@pytest.mark.parametrize(
    ("case", "display_name"),
    [
        ("the same spelling", COMPOSED),
        ("a decomposed spelling of the same name", DECOMPOSED),
        ("another case of the same name", "zo\u00cb"),
        ("a decomposed spelling in another case", "zoe\u0308"),
        ("the same name with surrounding spaces", f"  {COMPOSED}  "),
    ],
)
def test_a_name_that_conflicts_with_a_member_is_rejected(http: Http, case: str, display_name: str) -> None:
    """`conflict_key` is NFC over the casefolded value, so none of these may be seated beside the host."""
    assert http.error(http.join(display_name=display_name, seat=2)) == (409, "DISPLAY_NAME_TAKEN", "display_name")
    assert _occupant_names(http) == {1: COMPOSED}


# --- The seat (ADR 0009 §4 Field rules) ---


@pytest.mark.parametrize(
    ("case", "seat"),
    [("zero", 0), ("negative", -1), ("ten", 10), ("a boolean", True), ("a string", "2"), ("a float", 2.0)],
)
def test_a_seat_outside_the_product_range_is_a_validation_failure(http: Http, case: str, seat: object) -> None:
    """A seat outside 1-9, or of the wrong JSON type, is body validation: `VALIDATION_FAILED` with the field."""
    assert http.error(http.join(display_name="Bob", seat=seat)) == (422, "VALIDATION_FAILED", "seat")
    assert _occupant_names(http) == {1: COMPOSED}


@pytest.mark.parametrize("seat", [7, 8, 9])
def test_a_seat_inside_the_product_range_but_above_this_table_is_invalid_seat(http: Http, seat: int) -> None:
    """The two 422s are different codes: `INVALID_SEAT` is this table's `max_seats`, not the product range."""
    assert http.error(http.join(display_name="Bob", seat=seat)) == (422, "INVALID_SEAT", "seat")
    assert _occupant_names(http) == {1: COMPOSED}


def test_the_last_seat_of_the_table_is_accepted(http: Http) -> None:
    assert http.join(display_name="Bob", seat=6).status_code == 201
    assert set(_occupant_names(http)) == {1, 6}


def test_the_ninth_seat_is_accepted_at_a_nine_seat_table(make_app: Callable[..., Any]) -> None:
    harness = make_app(max_seats=9, new_table_id=lambda: TABLE_ID, new_join_code=lambda: JOIN_CODE)
    with TestClient(harness.app) as client:
        client.post("/tables", json={"display_name": "Alice"})
        joined = client.post(f"/tables/by-code/{JOIN_CODE}/members", json={"display_name": "Ivan", "seat": 9})
        assert joined.status_code == 201
        assert joined.json()["seat"] == 9


def test_an_occupied_seat_is_seat_taken(http: Http) -> None:
    assert http.error(http.join(display_name="Bob", seat=1)) == (409, "SEAT_TAKEN", "seat")


# --- The order of the checks (ADR 0009 §4) ---


def test_body_validation_comes_before_the_code_lookup(http: Http) -> None:
    """An unknown code with an unusable body answers the body's error, not `TABLE_NOT_FOUND`."""
    unknown = "/tables/by-code/ZZZZZZ/members"
    assert http.error(http.client.post(unknown, json={"display_name": "Bob", "seat": 99})) == (
        422,
        "VALIDATION_FAILED",
        "seat",
    )
    assert http.error(http.client.post(unknown, json={"display_name": "Bob"})) == (
        422,
        "VALIDATION_FAILED",
        "seat",
    )


def test_the_code_lookup_comes_before_the_domain_checks(http: Http) -> None:
    """A name and a seat that both conflict at the real table are not consulted for an unknown code."""
    unknown = http.client.post("/tables/by-code/ZZZZZZ/members", json={"display_name": COMPOSED, "seat": 1})
    assert http.error(unknown) == (404, "TABLE_NOT_FOUND", None)


def test_the_display_name_is_checked_before_the_seat(http: Http) -> None:
    """`TableSession`'s own order (ADR 0009 §4): a request that conflicts in both earns `DISPLAY_NAME_TAKEN`."""
    assert http.error(http.join(display_name=COMPOSED, seat=1)) == (409, "DISPLAY_NAME_TAKEN", "display_name")


# --- The join code (ADR 0009 §2, §4) ---


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("one character short", "K7Q2X"),
        ("one character long", "K7Q2XMM"),
        ("empty", " "),
        ("outside the alphabet", "K7Q20M"),
        ("another table's shape", "ZZZZZZ"),
        ("a confusable zero for the letter O", "K7Q2X0"),
    ],
)
def test_a_code_that_no_open_table_has_is_table_not_found(http: Http, case: str, code: str) -> None:
    """A malformed code and an unknown code are never distinguished (ADR 0009 §4)."""
    response = http.client.post(f"/tables/by-code/{code}/members", json={"display_name": "Bob", "seat": 2})
    assert http.error(response) == (404, "TABLE_NOT_FOUND", None)


def test_a_lowercase_code_reaches_the_same_table(http: Http) -> None:
    joined = http.client.post(f"/tables/by-code/{JOIN_CODE.lower()}/members", json={"display_name": "Bob", "seat": 2})
    assert joined.status_code == 201
    assert joined.json()["table_id"] == TABLE_ID


# --- The bodies and the error shape (ADR 0009 §4) ---


@pytest.mark.parametrize(
    ("case", "body"),
    [
        ("an extra field", {"display_name": "Bob", "seat": 2, "nickname": "B"}),
        ("a missing field", {"display_name": "Bob"}),
        ("an empty body", {}),
        ("a null name", {"display_name": None, "seat": 2}),
        ("a name that is not a string", {"display_name": 7, "seat": 2}),
        ("a nested name", {"display_name": {"value": "Bob"}, "seat": 2}),
    ],
)
def test_a_body_the_contract_forbids_is_a_validation_failure(http: Http, case: str, body: dict[str, Any]) -> None:
    status, code, _ = http.error(http.client.post(http.members, json=body))
    assert (status, code) == (422, "VALIDATION_FAILED")
    assert _occupant_names(http) == {1: COMPOSED}


def test_malformed_json_is_a_validation_failure_with_no_field(http: Http) -> None:
    response = http.client.post(
        http.members, content=b'{"display_name": "Bob", ', headers={"content-type": "application/json"}
    )
    assert http.error(response) == (422, "VALIDATION_FAILED", None)


def test_a_successful_response_also_carries_no_store(http: Http) -> None:
    created = http.client.post("/tables", json={"display_name": "Hostess"})
    assert created.status_code == 201
    assert created.headers["cache-control"] == "no-store"
    joined = http.join(display_name="Bob", seat=2)
    assert joined.status_code == 201
    assert joined.headers["cache-control"] == "no-store"


def test_a_create_response_carries_exactly_the_contracts_fields(http: Http) -> None:
    created = http.client.post("/tables", json={"display_name": "Hostess"})
    assert set(created.json()) == {"table_id", "join_code", "seat", "credential"}


def test_a_join_response_carries_exactly_the_contracts_fields(http: Http) -> None:
    joined = http.join(display_name="Bob", seat=2)
    assert set(joined.json()) == {"table_id", "seat", "credential"}


def test_no_user_id_reaches_any_http_response_body(http: Http) -> None:
    """ADR 0009 §2: a `UserId` never goes on the wire, and the credential only in these two bodies."""
    bodies = [
        http.client.post("/tables", json={"display_name": "Hostess"}).text,
        http.join(display_name="Bob", seat=2).text,
        http.join(display_name="Bob", seat=2).text,
        http.join(display_name="Cara", seat=99).text,
        http.client.post("/tables/by-code/ZZZZZZ/members", json={"display_name": "Cara", "seat": 3}).text,
    ]
    assert http.harness.minted_user_ids, "the harness must have minted at least one user id"
    for text in bodies:
        for forbidden in [*http.harness.minted_user_ids, "player_id", "user_id"]:
            assert forbidden not in text, f"{forbidden!r} leaked into an HTTP body"


def test_a_failed_join_seats_nobody_and_mints_no_credential(http: Http) -> None:
    """ADR 0009 §4: either the member is seated with the buy-in, or nothing changes (Brief §5.7)."""
    runtime = http.harness.directory.get(TABLE_ID)
    assert runtime is not None
    before = runtime.revision
    for body in (
        {"display_name": COMPOSED, "seat": 2},
        {"display_name": "Bob", "seat": 1},
        {"display_name": "Bob", "seat": 7},
        {"display_name": "", "seat": 2},
        {"display_name": "Bob", "seat": 0},
    ):
        response = http.client.post(http.members, json=body)
        assert response.status_code >= 400
        assert "credential" not in response.text
    assert runtime.revision == before
    assert _occupant_names(http) == {1: COMPOSED}


# --- `GET /health` is operational, not part of v1 ---


def test_the_health_probe_answers_exactly_its_body(http: Http) -> None:
    response = http.client.get("/health")
    assert (response.status_code, response.json()) == (200, {"status": "ok"})


def _occupant_names(http: Http) -> dict[int, str]:
    """Every seated member of the table, read from the host's own view through the runtime."""
    runtime = http.harness.directory.get(TABLE_ID)
    assert runtime is not None
    user_id = runtime.authenticate(http.harness.credentials[0])
    assert user_id is not None
    view = runtime.view_for(user_id)
    assert view is not None
    return {seat.number: seat.display_name.value for seat in view.seats if seat.display_name is not None}


# --- The `500 INTERNAL_ERROR` row of the contract's table (ADR 0009 §4) ---


@pytest.mark.parametrize(
    ("case", "answer"),
    [
        ("a rejection no join can earn", Rejected(RejectionCode.STALE_REVISION, "not the current revision")),
        ("a table that has just failed", None),
    ],
)
def test_an_answer_the_join_cannot_map_is_an_internal_error(
    http: Http, monkeypatch: pytest.MonkeyPatch, case: str, answer: object
) -> None:
    """The 500 row is unreachable by design, so the only way to check its body is to inject the answer.

    What matters is that even this answer is the contract's error body with no field, and not FastAPI's `detail`.
    """
    runtime = http.harness.directory.get(TABLE_ID)
    assert runtime is not None
    monkeypatch.setattr(runtime, "join", lambda *arguments, **keywords: answer)

    response = http.join(display_name="Bob", seat=2)

    assert http.error(response) == (500, "INTERNAL_ERROR", None)
    assert "credential" not in response.text
