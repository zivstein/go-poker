"""The variant-agnostic reveal record and seat ordering, on plain seat sequences."""

import dataclasses

import pytest

from go_poker.game.reveal import Reveal, RevealKind, canonical_seat_order, show_order

# Seats clockwise with the button first, as in `hand.players`: seat 4 is the button, 7 the small blind, 2 the big blind.
SEATS_FROM_BUTTON = (4, 7, 2, 9, 5)


def test_canonical_order_starts_left_of_the_button_and_ends_with_the_button() -> None:
    assert canonical_seat_order(SEATS_FROM_BUTTON) == (7, 2, 9, 5, 4)


def test_canonical_order_heads_up_starts_with_the_big_blind() -> None:
    """Heads-up the button is the small blind, so the big blind is the first seat left of it."""
    assert canonical_seat_order((3, 8)) == (8, 3)


def test_show_order_without_an_aggressor_is_the_live_seats_in_canonical_order() -> None:
    assert show_order(SEATS_FROM_BUTTON, {4, 7, 2, 9, 5}, None) == (7, 2, 9, 5, 4)


def test_show_order_starts_with_the_aggressor_and_goes_clockwise() -> None:
    assert show_order(SEATS_FROM_BUTTON, {4, 7, 2, 9, 5}, 9) == (9, 5, 4, 7, 2)


def test_show_order_wraps_past_the_button() -> None:
    """From seat 5 the order passes the button (4) and continues with the seats left of it."""
    assert show_order(SEATS_FROM_BUTTON, {4, 7, 2, 9, 5}, 5) == (5, 4, 7, 2, 9)


def test_show_order_starting_at_the_first_seat_left_of_the_button_is_canonical() -> None:
    assert show_order(SEATS_FROM_BUTTON, {4, 7, 2, 9, 5}, 7) == (7, 2, 9, 5, 4)


def test_show_order_skips_folded_seats() -> None:
    assert show_order(SEATS_FROM_BUTTON, {4, 2, 5}, None) == (2, 5, 4)
    assert show_order(SEATS_FROM_BUTTON, {4, 2, 5}, 5) == (5, 4, 2)


def test_show_order_does_not_change_its_inputs() -> None:
    live = {4, 2}
    show_order(SEATS_FROM_BUTTON, live, 4)

    assert SEATS_FROM_BUTTON == (4, 7, 2, 9, 5)
    assert live == {4, 2}


def test_a_reveal_is_immutable() -> None:
    reveal = Reveal(RevealKind.SHOWDOWN, (2, 3, 1))

    with pytest.raises(dataclasses.FrozenInstanceError):
        reveal.kind = RevealKind.ALL_IN  # type: ignore[misc]
    assert reveal == Reveal(RevealKind.SHOWDOWN, (2, 3, 1))
    assert reveal != Reveal(RevealKind.ALL_IN, (2, 3, 1))
