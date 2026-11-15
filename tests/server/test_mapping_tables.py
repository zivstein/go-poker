"""Every enum table in `mapping` is exhaustive in both directions (ADR 0008 §2, ADR 0009 §3, §12).

- every member of the engine enum is a key, so a new engine value fails here instead of reaching the wire as a
  `KeyError` at runtime;
- every value of the wire enum is produced by some engine value, so no wire string is unreachable or misspelled.

Together they are the guard that keeps the two sets of names apart: the wire's strings are never derived from an
engine enum's `.value` or `.name`.
"""

from collections.abc import Mapping
from enum import Enum
from typing import Any, get_args

import pytest

from go_poker.app.pre_actions import PreActionKind
from go_poker.app.results import RejectionCode, TransitionCause
from go_poker.app.views import TablePhase
from go_poker.core.card import Rank, Suit
from go_poker.core.hand_rank import HandCategory
from go_poker.game.betting.actions import ActionType
from go_poker.game.position import Blind, Position
from go_poker.game.showdown import ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.view import OccupantStatus, TurnKind
from go_poker.server import dto, mapping

ENUM_TABLES: tuple[tuple[str, Mapping[Any, Any], type[Enum]], ...] = (
    ("RANKS", mapping.RANKS, Rank),
    ("SUITS", mapping.SUITS, Suit),
    ("PHASES", mapping.PHASES, TablePhase),
    ("STREETS", mapping.STREETS, Street),
    ("POSITIONS", mapping.POSITIONS, Position),
    ("BLINDS", mapping.BLINDS, Blind),
    ("TURN_KINDS", mapping.TURN_KINDS, TurnKind),
    ("SHOWDOWN_KINDS", mapping.SHOWDOWN_KINDS, ShowdownKind),
    ("SHOWDOWN_DECISIONS", mapping.SHOWDOWN_DECISIONS, ShowdownAction),
    ("HAND_CATEGORIES", mapping.HAND_CATEGORIES, HandCategory),
    ("PRE_ACTION_KINDS", mapping.PRE_ACTION_KINDS, PreActionKind),
    ("ACTIONS", mapping.ACTIONS, ActionType),
    ("REJECTED_CODES", mapping.REJECTED_CODES, RejectionCode),
    ("TRANSITION_CAUSES", mapping.TRANSITION_CAUSES, TransitionCause),
)

WIRE_ENUMS: tuple[tuple[str, Mapping[Any, Any], object], ...] = (
    ("PHASES", mapping.PHASES, dto.Phase),
    ("STREETS", mapping.STREETS, dto.Street),
    ("POSITIONS", mapping.POSITIONS, dto.Position),
    ("BLINDS", mapping.BLINDS, dto.Blind),
    ("OCCUPANT_STATUSES", mapping.OCCUPANT_STATUSES, dto.OccupantStatus),
    ("TURN_KINDS", mapping.TURN_KINDS, dto.TurnKind),
    ("SHOWDOWN_KINDS", mapping.SHOWDOWN_KINDS, dto.ShowdownKind),
    ("SHOWDOWN_DECISIONS", mapping.SHOWDOWN_DECISIONS, dto.ShowdownDecision),
    ("HAND_CATEGORIES", mapping.HAND_CATEGORIES, dto.HandCategory),
    ("PRE_ACTION_KINDS", mapping.PRE_ACTION_KINDS, dto.PreActionKind),
    ("ACTIONS", mapping.ACTIONS, dto.Action),
    ("REJECTED_CODES", mapping.REJECTED_CODES, dto.RejectedCode),
)


@pytest.mark.parametrize(("name", "table", "enum"), ENUM_TABLES, ids=[name for name, _, _ in ENUM_TABLES])
def test_a_table_has_a_key_for_every_member_of_its_engine_enum(
    name: str, table: Mapping[Any, Any], enum: type[Enum]
) -> None:
    assert set(table) == set(enum), f"{name} does not cover {enum.__name__}"


def test_the_occupant_status_table_also_maps_the_ready_occupant() -> None:
    """A ready occupant's status is already None in the engine's view, and stays null on the wire."""
    assert set(mapping.OCCUPANT_STATUSES) == {None, *OccupantStatus}
    assert mapping.OCCUPANT_STATUSES[None] is None


@pytest.mark.parametrize(("name", "table", "wire_enum"), WIRE_ENUMS, ids=[name for name, _, _ in WIRE_ENUMS])
def test_a_table_produces_every_value_of_its_wire_enum(name: str, table: Mapping[Any, Any], wire_enum: object) -> None:
    produced = {value for value in table.values() if value is not None}
    assert produced == set(get_args(wire_enum)), f"{name} does not produce every value of its wire enum"


def test_the_transition_causes_are_the_wire_causes_that_a_shared_transition_can_have() -> None:
    """`connected` and `private` are the server's own causes, not a transition's (ADR 0009 §9)."""
    assert set(mapping.TRANSITION_CAUSES.values()) | {mapping.CONNECTED, mapping.PRIVATE} == set(
        get_args(dto.SnapshotCause)
    )
    assert mapping.CONNECTED not in mapping.TRANSITION_CAUSES.values()
    assert mapping.PRIVATE not in mapping.TRANSITION_CAUSES.values()


def test_the_codes_that_never_reach_a_rejected_message_are_the_http_join_codes() -> None:
    """ADR 0009 §12: the five join codes occur only on the HTTP join, and `NOT_AT_HAND_BOUNDARY` is internal."""
    assert {code.name for code, wire in mapping.REJECTED_CODES.items() if wire is None} == {
        "ALREADY_MEMBER",
        "LEFT_TABLE",
        "DISPLAY_NAME_TAKEN",
        "SEAT_TAKEN",
        "INVALID_SEAT",
        "NOT_AT_HAND_BOUNDARY",
    }


def test_the_rank_and_suit_characters_are_the_contracts_alphabets() -> None:
    assert "".join(mapping.RANKS[rank] for rank in Rank) == "23456789TJQKA"
    assert "".join(mapping.SUITS[suit] for suit in Suit) == "cdhs"


INVERSE_TABLES: tuple[tuple[str, Mapping[Any, Any], Mapping[Any, Any]], ...] = (
    ("ACTIONS", mapping.ACTIONS, mapping.WIRE_ACTIONS),
    ("SHOWDOWN_DECISIONS", mapping.SHOWDOWN_DECISIONS, mapping.WIRE_SHOWDOWN_DECISIONS),
    ("PRE_ACTION_KINDS", mapping.PRE_ACTION_KINDS, mapping.WIRE_PRE_ACTION_KINDS),
)


@pytest.mark.parametrize(("name", "outbound", "inbound"), INVERSE_TABLES, ids=[name for name, _, _ in INVERSE_TABLES])
def test_an_inbound_table_is_the_exact_inverse_of_its_outbound_table(
    name: str, outbound: Mapping[Any, Any], inbound: Mapping[Any, Any]
) -> None:
    """The two directions are written out separately, so each must cover the other completely."""
    assert {wire: engine for engine, wire in outbound.items()} == inbound, f"{name} and its inverse disagree"
    assert {engine: wire for wire, engine in inbound.items()} == outbound


@pytest.mark.parametrize(
    ("name", "table", "wire_enum"),
    [
        ("WIRE_ACTIONS", mapping.WIRE_ACTIONS, dto.Action),
        ("WIRE_SHOWDOWN_DECISIONS", mapping.WIRE_SHOWDOWN_DECISIONS, dto.ShowdownDecision),
        ("WIRE_PRE_ACTION_KINDS", mapping.WIRE_PRE_ACTION_KINDS, dto.PreActionKind),
    ],
    ids=["WIRE_ACTIONS", "WIRE_SHOWDOWN_DECISIONS", "WIRE_PRE_ACTION_KINDS"],
)
def test_an_inbound_table_has_a_key_for_every_value_of_its_wire_enum(
    name: str, table: Mapping[Any, Any], wire_enum: object
) -> None:
    assert set(table) == set(get_args(wire_enum)), f"{name} does not cover its wire enum"
