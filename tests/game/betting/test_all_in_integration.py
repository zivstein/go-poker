"""Milestone 3 short all-in scenarios driven through the public dealing and betting operations.

Hands are built the way hand setup builds them (the conftest `make_hand`) at blinds 50/100. Every step re-checks the
betting invariants (see `CheckedHand.check` in the conftest), including that a player is all-in exactly when their stack
is empty.

Unmatched chips are not returned and chips in front are not collected yet: when a round completes, every street
contribution stays in front until the next round starts, and an uncalled excess stays in the player's total
contribution.
"""

from collections.abc import Callable
from typing import Any

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.legal_actions import LegalActions, legal_actions
from go_poker.game.betting.rounds import is_betting_closed, is_round_complete
from go_poker.game.betting.stakes import Stakes
from go_poker.game.poker_hand import PokerHand
from go_poker.game.street import Street

# The conftest `CheckedHand`, which test modules cannot import.
type CheckedHand = Any
type HandFactory = Callable[..., PokerHand]

STAKES = Stakes(small_blind=50, big_blind=100)

FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)


def bet(target: int) -> Action:
    return Action(ActionType.BET, target)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def legal(
    *,
    can_check: bool = False,
    can_call: bool = False,
    amount_owed: int = 0,
    call_amount: int = 0,
    call_is_all_in: bool = False,
    can_bet: bool = False,
    can_raise: bool = False,
    min_full_target: int | None = None,
    max_target: int | None = None,
    short_all_in_target: int | None = None,
) -> LegalActions:
    """Expected legal actions for a current actor, who may always fold; anything not given is not legal or set."""
    return LegalActions(
        can_fold=True,
        can_check=can_check,
        can_call=can_call,
        amount_owed=amount_owed,
        call_amount=call_amount,
        call_is_all_in=call_is_all_in,
        can_bet=can_bet,
        can_raise=can_raise,
        min_full_target=min_full_target,
        max_target=max_target,
        short_all_in_target=short_all_in_target,
    )


def in_front(h: CheckedHand) -> dict[int, int]:
    return {seat: hp.street_contribution for seat, hp in h.seats.items()}


def stacks(h: CheckedHand) -> dict[int, int]:
    return {seat: hp.player.stack for seat, hp in h.seats.items()}


def totals(h: CheckedHand) -> dict[int, int]:
    return {seat: hp.total_contribution for seat, hp in h.seats.items()}


THREE_HANDED_BUTTON = 1  # seats 1 (button), 2 (small blind), 3 (big blind); seat 2 acts first after the flop
FOUR_HANDED_BUTTON = 5  # seats 5 (button), 8 (small blind), 1 (big blind), 3 (UTG); seat 8 acts first after the flop


def called_around_to_the_flop(checked: Callable[[PokerHand], CheckedHand], hand: PokerHand) -> CheckedHand:
    """Three-handed: the button and small blind call the big blind, the big blind checks, and the flop round starts."""
    h = checked(hand)
    h.start(STAKES)
    h.act((1, CALL), (2, CALL), (3, CHECK))
    h.next_street()
    return h


# =============================================================================
# SHORT CALL
# =============================================================================


def test_short_all_in_call_leaves_the_current_bet_and_the_raiser_s_excess_in_front(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """On the flop the small blind bets 100, the big blind raises to 500 and the button folds. The small blind owes
    400 but has only 150 behind, so its call is all-in for 150. The current bet stays 500, the round is complete with
    the big blind's uncalled 250 still in front, and no further betting is possible."""
    h = called_around_to_the_flop(
        checked, make_hand({1: 1000, 2: 350, 3: 1000}, button_seat_number=THREE_HANDED_BUTTON)
    )
    h.act((2, bet(100)), (3, raise_to(500)), (1, FOLD))

    assert legal_actions(h.hand) == legal(can_call=True, amount_owed=400, call_amount=150, call_is_all_in=True)
    h.act((2, CALL))

    assert h.seats[2].all_in is True
    assert (h.betting.current_bet, h.betting.last_full_raise_size) == (500, 400)
    assert is_round_complete(h.betting)
    assert is_betting_closed(h.hand)
    assert in_front(h) == {1: 0, 2: 250, 3: 500}
    assert stacks(h) == {1: 900, 2: 0, 3: 400}

    h.next_street()  # the turn round starts complete; the excess stays committed
    assert (h.betting.current_actor, h.betting.pending_actors) == (None, set())
    assert totals(h) == {1: 100, 2: 350, 3: 600}
    assert is_betting_closed(h.hand)


# =============================================================================
# SHORT OPENING BET
# =============================================================================


def test_short_all_in_opening_bet_keeps_the_full_raise_size_for_the_next_raise(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """On the flop the small blind has 30, less than the full bet of 100, and can only open all-in for 30. The current
    bet becomes 30 and the last full raise size stays 100, so the big blind's minimum raise is to 130. After the
    button calls, the all-in small blind is skipped when the turn round starts."""
    h = called_around_to_the_flop(
        checked, make_hand({1: 1000, 2: 130, 3: 1000}, button_seat_number=THREE_HANDED_BUTTON)
    )
    assert legal_actions(h.hand) == legal(
        can_check=True, can_bet=True, min_full_target=100, max_target=30, short_all_in_target=30
    )
    h.act((2, bet(30)))
    assert (h.betting.current_bet, h.betting.last_full_raise_size) == (30, 100)
    assert (h.betting.current_actor, h.betting.pending_actors) == (3, {3, 1})

    assert legal_actions(h.hand) == legal(
        can_call=True, amount_owed=30, call_amount=30, can_raise=True, min_full_target=130, max_target=900
    )
    h.act((3, raise_to(130)), (1, CALL))
    assert (h.betting.current_bet, h.betting.last_full_raise_size) == (130, 100)
    assert is_round_complete(h.betting)
    assert not is_betting_closed(h.hand)
    assert in_front(h) == {1: 130, 2: 30, 3: 130}

    h.next_street()
    assert (h.betting.current_actor, h.betting.pending_actors) == (3, {3, 1})


# =============================================================================
# SHORT RAISE AND REOPENING
# =============================================================================


def test_short_all_in_raise_does_not_reopen_raising_for_the_bettor(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """On the flop the small blind bets 100 and the big blind raises all-in to 170, below the minimum raise to 200.
    The button, yet to act, may still raise to the full minimum of 270, but calls. The small blind acted at 100 and
    faces only 70 more, less than the full raise size of 100, so it may only call or fold."""
    h = called_around_to_the_flop(
        checked, make_hand({1: 1000, 2: 1000, 3: 270}, button_seat_number=THREE_HANDED_BUTTON)
    )
    h.act((2, bet(100)))
    assert legal_actions(h.hand) == legal(
        can_call=True,
        amount_owed=100,
        call_amount=100,
        can_raise=True,
        min_full_target=200,
        max_target=170,
        short_all_in_target=170,
    )
    h.act((3, raise_to(170)))
    assert (h.betting.current_bet, h.betting.last_full_raise_size) == (170, 100)
    assert h.betting.pending_actors == {1, 2}

    assert legal_actions(h.hand) == legal(
        can_call=True, amount_owed=170, call_amount=170, can_raise=True, min_full_target=270, max_target=900
    )
    h.act((1, CALL))
    assert legal_actions(h.hand) == legal(can_call=True, amount_owed=70, call_amount=70)
    h.act((2, CALL))

    assert is_round_complete(h.betting)
    assert in_front(h) == {1: 170, 2: 170, 3: 170}


def test_cumulative_short_all_ins_reopen_raising_only_for_a_full_raise_since_acting(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """On the flop the small blind bets 100, the big blind goes all-in to 160, UTG calls 160 and the button goes all-in
    to 200, each all-in below the minimum raise. The small blind acted at 100 and now faces 100 more, a full raise in
    total, so it may raise to at least 300; it calls. UTG acted at 160 and faces only 40 more, so it may only call or
    fold. The last full raise size stays 100 throughout."""
    h = checked(make_hand({5: 300, 8: 1000, 1: 260, 3: 1000}, button_seat_number=FOUR_HANDED_BUTTON))
    h.start(STAKES)
    h.act((3, CALL), (5, CALL), (8, CALL), (1, CHECK))
    h.next_street()

    h.act((8, bet(100)), (1, raise_to(160)), (3, CALL))
    assert legal_actions(h.hand) == legal(
        can_call=True,
        amount_owed=160,
        call_amount=160,
        can_raise=True,
        min_full_target=260,
        max_target=200,
        short_all_in_target=200,
    )
    h.act((5, raise_to(200)))
    assert (h.betting.current_bet, h.betting.last_full_raise_size) == (200, 100)
    assert h.betting.acted_at_bet == {8: 100, 1: 160, 3: 160, 5: 200}

    assert h.betting.current_actor == 8
    assert legal_actions(h.hand) == legal(
        can_call=True, amount_owed=100, call_amount=100, can_raise=True, min_full_target=300, max_target=900
    )
    h.act((8, CALL))
    assert h.betting.current_actor == 3
    assert legal_actions(h.hand) == legal(can_call=True, amount_owed=40, call_amount=40)
    h.act((3, CALL))

    assert is_round_complete(h.betting)
    assert in_front(h) == {5: 200, 8: 200, 1: 160, 3: 200}
    assert totals(h) == {5: 300, 8: 300, 1: 260, 3: 300}


def test_checker_facing_a_short_all_in_opening_bet_may_not_raise(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """On the flop the small blind checks and the big blind bets all-in for 30, below the full bet of 100. The button,
    yet to act, may raise to the full minimum of 130, but calls. The small blind checked at 0 and faces only 30 more,
    so it may only call or fold."""
    h = called_around_to_the_flop(
        checked, make_hand({1: 1000, 2: 1000, 3: 130}, button_seat_number=THREE_HANDED_BUTTON)
    )
    h.act((2, CHECK), (3, bet(30)))
    assert (h.betting.current_bet, h.betting.last_full_raise_size) == (30, 100)

    assert legal_actions(h.hand) == legal(
        can_call=True, amount_owed=30, call_amount=30, can_raise=True, min_full_target=130, max_target=900
    )
    h.act((1, CALL))
    assert legal_actions(h.hand) == legal(can_call=True, amount_owed=30, call_amount=30)
    h.act((2, CALL))

    assert is_round_complete(h.betting)
    assert in_front(h) == {1: 30, 2: 30, 3: 30}


# =============================================================================
# SHORT BLINDS
# =============================================================================


def test_short_big_blind_multiway_keeps_the_nominal_big_blind_and_is_never_pending(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """Four-handed, the big blind is all-in for 30 of the 100 blind. The others still owe the full 100 and the minimum
    raise is to 200; UTG calls, the button raises to 300, the small blind folds and UTG calls. The big blind never
    owes an action, and on the flop UTG is the first player able to act."""
    h = checked(make_hand({5: 1000, 8: 1000, 1: 30, 3: 1000}, button_seat_number=FOUR_HANDED_BUTTON))
    h.start(STAKES)
    assert (h.seats[1].player.stack, h.seats[1].street_contribution, h.seats[1].all_in) == (0, 30, True)
    assert (h.betting.current_bet, h.betting.last_full_raise_size) == (100, 100)
    assert (h.betting.current_actor, h.betting.pending_actors) == (3, {3, 5, 8})

    assert legal_actions(h.hand) == legal(
        can_call=True, amount_owed=100, call_amount=100, can_raise=True, min_full_target=200, max_target=1000
    )
    h.act((3, CALL), (5, raise_to(300)), (8, FOLD), (3, CALL))
    assert is_round_complete(h.betting)
    assert in_front(h) == {5: 300, 8: 50, 1: 30, 3: 300}

    h.next_street()
    assert (h.betting.current_actor, h.betting.pending_actors) == (3, {3, 5})
    h.act((3, CHECK), (5, CHECK))
    assert is_round_complete(h.betting)


def test_heads_up_short_big_blind_is_called_for_what_it_can_contest(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """Heads-up, the big blind is all-in for 70 of the 100 blind. The small blind, with 50 in, owes only 20, not the
    nominal 50 more: it calls 20, both have 70 in front, the current bet stays 100 and no further betting is
    possible. Every later round starts complete."""
    h = checked(make_hand({3: 70, 7: 1000}, button_seat_number=7))
    h.start(STAKES)
    assert (h.betting.current_actor, h.betting.pending_actors) == (7, {7})

    assert legal_actions(h.hand) == legal(can_call=True, amount_owed=20, call_amount=20)
    h.act((7, CALL))

    assert in_front(h) == {7: 70, 3: 70}
    assert stacks(h) == {7: 930, 3: 0}
    assert h.betting.current_bet == 100
    assert is_round_complete(h.betting)
    assert is_betting_closed(h.hand)

    for street in (Street.FLOP, Street.TURN, Street.RIVER):
        h.next_street()
        assert h.betting.street is street
        assert (h.betting.current_actor, h.betting.pending_actors) == (None, set())
        assert is_betting_closed(h.hand)


# =============================================================================
# AN ALL-IN DOES NOT END THE HAND
# =============================================================================


def test_short_all_in_player_is_skipped_while_deeper_players_keep_betting(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """UTG raises all-in to 150 preflop, below the minimum raise to 200. The big blind, yet to act, makes a full raise
    to 400 and the others call. On the flop, turn and river the deeper players keep betting and raising, and one of
    them folds; UTG is never pending or to act again. On the river two players can still act, so betting is not
    closed even with the round complete."""
    h = checked(make_hand({5: 2000, 8: 2000, 1: 2000, 3: 150}, button_seat_number=FOUR_HANDED_BUTTON))
    h.start(STAKES)
    h.act((3, raise_to(150)), (5, CALL), (8, CALL))
    assert (h.betting.current_bet, h.betting.last_full_raise_size) == (150, 100)
    assert legal_actions(h.hand) == legal(
        can_call=True, amount_owed=50, call_amount=50, can_raise=True, min_full_target=250, max_target=2000
    )
    h.act((1, raise_to(400)))
    assert (h.betting.last_full_raise_size, h.betting.pending_actors) == (250, {5, 8})
    h.act((5, CALL), (8, CALL))
    assert in_front(h) == {5: 400, 8: 400, 1: 400, 3: 150}

    h.next_street()
    assert (h.betting.current_actor, h.betting.pending_actors) == (8, {8, 1, 5})
    h.act((8, CHECK), (1, bet(300)), (5, raise_to(900)), (8, FOLD), (1, CALL))

    h.next_street()
    assert (h.betting.current_actor, h.betting.pending_actors) == (1, {1, 5})
    h.act((1, CHECK), (5, bet(500)), (1, CALL))

    h.next_street()
    assert (h.betting.current_actor, h.betting.pending_actors) == (1, {1, 5})
    h.act((1, CHECK), (5, CHECK))

    assert is_round_complete(h.betting)
    assert not is_betting_closed(h.hand)
    assert totals(h) == {5: 1800, 8: 400, 1: 1800, 3: 150}
    assert stacks(h) == {5: 200, 8: 1600, 1: 200, 3: 0}
