"""The HTTP surface: create a table, join a table, and the operational health probe (ADR 0009 §4).

The order of checks is the contract's, and it is visible in one place in each handler:

1. **the body's shape**, which FastAPI decides with `dto.CreateTableRequest` / `dto.JoinTableRequest`; a failure
   arrives here as a `RequestValidationError` and becomes `422 VALIDATION_FAILED`;
2. **the display name's format**, which is the application layer's own rule (`DisplayName` NFC-normalizes, trims,
   requires 1-20 characters and rejects Unicode category C). It is constructed here and its `ValueError` becomes
   `422 VALIDATION_FAILED`; the rule itself is never reimplemented;
3. **the join code's lookup**, where a miss is `404 TABLE_NOT_FOUND`. An unknown code, a malformed code, a failed
   table and a closed session are never distinguished;
4. **the domain**, `TableRuntime.join`, whose rejection maps through `JOIN_REJECTIONS` below.

Every non-2xx answer of these two endpoints, a server defect included (`500 INTERNAL_ERROR`, through
`handle_server_defect`), is the contract's error body, `{"error": {"code", "message", "field"}}`, and never
FastAPI's default `{"detail": ...}` or Starlette's plain-text 500. `message` is a diagnostic: it is English text for
logs and is not normative (ADR 0009 §7). A route outside these endpoints is not part of v1 and keeps Starlette's
own answer.
"""

from collections.abc import Mapping

from fastapi import APIRouter, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from go_poker.app.identity import DisplayName
from go_poker.app.results import Rejected, RejectionCode
from go_poker.server import dto
from go_poker.server.directory import TableDirectory

CREATED = 201

# The join's domain rejections: status, wire code and offending field (ADR 0009 §4). `ALREADY_MEMBER` and
# `LEFT_TABLE` are mapped for completeness and are unreachable in v1, because every join mints a fresh identity.
JOIN_REJECTIONS: Mapping[RejectionCode, tuple[int, dto.HttpErrorCode, str | None]] = {
    RejectionCode.DISPLAY_NAME_TAKEN: (409, "DISPLAY_NAME_TAKEN", "display_name"),
    RejectionCode.SEAT_TAKEN: (409, "SEAT_TAKEN", "seat"),
    RejectionCode.INVALID_SEAT: (422, "INVALID_SEAT", "seat"),
    RejectionCode.ALREADY_MEMBER: (409, "ALREADY_MEMBER", None),
    RejectionCode.LEFT_TABLE: (409, "LEFT_TABLE", None),
}

# The fields a request body may name. A validation error whose location ends in one of them reports it; anything
# else, malformed JSON included, reports no field.
BODY_FIELDS = frozenset({*dto.CreateTableRequest.model_fields, *dto.JoinTableRequest.model_fields})

router = APIRouter()


class ApiError(Exception):
    """One non-2xx HTTP answer of this API, as the contract's error body."""

    def __init__(self, status: int, code: dto.HttpErrorCode, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.field = field


def error_response(status: int, code: dto.HttpErrorCode, message: str, field: str | None) -> JSONResponse:
    body = dto.ErrorBody(error=dto.ErrorDetail(code=code, message=message, field=field))
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"))


async def handle_api_error(request: Request, exception: Exception) -> Response:
    """Render an `ApiError` as the contract's error body."""
    assert isinstance(exception, ApiError)
    return error_response(exception.status, exception.code, exception.message, exception.field)


async def handle_server_defect(request: Request, exception: Exception) -> Response:
    """Answer an unexpected exception as `500 INTERNAL_ERROR`, field null (ADR 0009 §4), with `no-store`.

    Starlette installs a handler for `Exception` in its `ServerErrorMiddleware`, which sits *outside* the user
    middleware stack, so the app's `no_store` middleware never wraps this response: the header is set here. The
    message is fixed, because an exception's text can carry internals. Starlette re-raises the exception after this
    response is sent, so the defect still reaches the server's log; nothing is swallowed.
    """
    response = error_response(500, "INTERNAL_ERROR", "The server hit a defect", None)
    response.headers["Cache-Control"] = "no-store"
    return response


async def handle_validation_error(request: Request, exception: Exception) -> Response:
    """Replace FastAPI's default `422 {"detail": ...}` with `422 VALIDATION_FAILED` and the contract's body."""
    assert isinstance(exception, RequestValidationError)
    errors = exception.errors()
    first = errors[0] if errors else {}
    location = first.get("loc") or ()
    last = location[-1] if location else None
    field = last if isinstance(last, str) and last in BODY_FIELDS else None
    message = str(first.get("msg", "The request body is not valid"))
    return error_response(422, "VALIDATION_FAILED", message, field)


def _directory(request: Request) -> TableDirectory:
    directory = request.app.state.directory
    assert isinstance(directory, TableDirectory)
    return directory


def _display_name(value: str) -> DisplayName:
    """Check 2: the application layer's display-name rule, raised as a validation failure."""
    try:
        return DisplayName(value)
    except ValueError as error:
        raise ApiError(422, "VALIDATION_FAILED", str(error), "display_name") from error


def _join_rejection(rejected: Rejected) -> ApiError:
    """Check 4's answer: the rejection's own status, code and field, with the application's message passed through."""
    mapped = JOIN_REJECTIONS.get(rejected.code)
    if mapped is None:  # No other rejection can reach a join: the server supplies the current revision (C6.1 E4).
        return ApiError(500, "INTERNAL_ERROR", f"Unexpected rejection {rejected.code.name}", None)
    status, code, field = mapped
    return ApiError(status, code, rejected.message, field)


@router.get("/health")
async def health() -> dict[str, str]:
    """Operational, not part of `go-poker.v1` (ADR 0009 §4)."""
    return {"status": "ok"}


@router.post("/tables", status_code=CREATED)
async def create_table(request: Request, body: dto.CreateTableRequest) -> dto.CreateTableResponse:
    """Create a table. The creator is seated as host, `waiting_to_join`, with the buy-in."""
    display_name = _display_name(body.display_name)
    created = _directory(request).create(display_name)
    return dto.CreateTableResponse(
        table_id=created.runtime.table_id,
        join_code=created.runtime.join_code,
        seat=created.seat,
        credential=created.credential,
    )


@router.post("/tables/by-code/{join_code}/members", status_code=CREATED)
async def join_table(request: Request, join_code: str, body: dto.JoinTableRequest) -> dto.JoinTableResponse:
    """Join a table by its code and sit at `seat` with the buy-in. Either the member is seated, or nothing changed."""
    display_name = _display_name(body.display_name)
    runtime = _directory(request).by_code(join_code)
    if runtime is None:
        raise ApiError(404, "TABLE_NOT_FOUND", "No open table has this code", None)
    joined = runtime.join(display_name, body.seat)
    if joined is None:
        raise ApiError(500, "INTERNAL_ERROR", "The table is no longer available", None)
    if isinstance(joined, Rejected):
        raise _join_rejection(joined)
    return dto.JoinTableResponse(table_id=runtime.table_id, seat=joined.seat, credential=joined.credential)
