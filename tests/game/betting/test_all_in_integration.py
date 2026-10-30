"""Milestone 3 all-in and chip-accounting scenarios driven through the public dealing and betting operations.

Hands are built the way hand setup builds them (the conftest `make_hand`) at blinds 50/100. Every step re-checks the
betting and accounting invariants (see `CheckedHand.check` in the conftest), including that a player is all-in exactly
when their stack is empty, that every committed chip is either in front of a player or in the middle pot, that the pots
add up to the middle pot, and that a completed round has been collected: nothing is left in front and the highest total
contribution is matched.
"""

from collections.abc import Callable
from typing import Any

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.legal_actions import LegalActions, legal_actions
from go_poker.game.betting.pots import Pot, middle_pot, pots
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


def pot(amount: int, *eligible_seats: int) -> Pot:
    return Pot(amount, frozenset(eligible_seats))


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


def test_short_all_in_call_leaves_the_current_bet_and_returns_the_raiser_s_uncalled_excess(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """On the flop the small blind bets 100, the big blind raises to 500 and the button folds. The small blind owes
    400 but has only 150 behind, so its call is all-in for 150. The current bet stays 500 and the round is complete:
    the collection returns the big blind's 250 that the call could not match and moves the matched chips into the
    middle, and no further betting is possible."""
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
    assert in_front(h) == {1: 0, 2: 0, 3: 0}
    assert stacks(h) == {1: 900, 2: 0, 3: 650}
    assert totals(h) == {1: 100, 2: 350, 3: 350}
    assert middle_pot(h.hand) == 800
    assert pots(h.hand) == (pot(300, 2, 3), pot(500, 2, 3))  # the folded button's 100 is a layer boundary

    h.next_street()  # the turn round starts complete, with nothing to collect
    assert (h.betting.current_actor, h.betting.pending_actors) == (None, set())
    assert totals(h) == {1: 100, 2: 350, 3: 350}
    assert is_betting_closed(h.hand)


# =============================================================================
# SHORT OPENING BET
# =============================================================================


def test_short_all_in_opening_bet_keeps_the_full_raise_size_for_the_next_raise(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """On the flop the small blind has 30, less than the full bet of 100, and can only open all-in for 30. The current
    bet becomes 30 and the last full raise size stays 100, so the big blind's minimum raise is to 130. After the
    button calls, the all-in small blind is eligible only for the main pot its 130 reach, and it is skipped when the
    turn round starts."""
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
    assert totals(h) == {1: 230, 2: 130, 3: 230}
    assert pots(h.hand) == (pot(390, 1, 2, 3), pot(200, 1, 3))

    h.next_street()
    assert (h.betting.current_actor, h.betting.pending_actors) == (3, {3, 1})


# =============================================================================
# SHORT RAISE AND REOPENING
# =============================================================================


def test_short_all_in_raise_makes_earlier_actors_respond_without_reopening_raising(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """Four-handed on the flop: the small blind bets 100, the big blind calls, and UTG raises all-in to 170, below
    the minimum raise to 200. Every other player owes a response again, but the raise is short, so the last full raise
    size stays 100. The button, yet to act, may still raise to the full minimum of 270, but calls. The bettor and the
    caller both acted at 100 and face only 70 more, less than a full raise: each is pending and may call the 70 or
    fold, but not raise."""
    h = checked(make_hand({5: 1000, 8: 1000, 1: 1000, 3: 270}, button_seat_number=FOUR_HANDED_BUTTON))
    h.start(STAKES)
    h.act((3, CALL), (5, CALL), (8, CALL), (1, CHECK))
    h.next_street()

    h.act((8, bet(100)), (1, CALL))
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
    assert (h.betting.current_actor, h.betting.pending_actors) == (5, {5, 8, 1})

    assert legal_actions(h.hand) == legal(
        can_call=True, amount_owed=170, call_amount=170, can_raise=True, min_full_target=270, max_target=900
    )
    h.act((5, CALL))
    assert (h.betting.current_actor, h.betting.pending_actors) == (8, {8, 1})
    assert legal_actions(h.hand) == legal(can_call=True, amount_owed=70, call_amount=70)
    h.act((8, CALL))
    assert (h.betting.current_actor, h.betting.pending_actors) == (1, {1})
    assert legal_actions(h.hand) == legal(can_call=True, amount_owed=70, call_amount=70)
    h.act((1, CALL))

    assert is_round_complete(h.betting)
    assert totals(h) == {5: 270, 8: 270, 1: 270, 3: 270}
    assert pots(h.hand) == (pot(1080, 5, 8, 1, 3),)


def test_cumulative_short_all_ins_reopen_raising_only_for_a_full_raise_since_acting(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """On the flop the small blind bets 100, the big blind goes all-in to 160, UTG calls 160 and the button goes all-in
    to 200, each all-in below the minimum raise. Each short all-in makes every other player who can act owe a
    response, and the last full raise size stays 100 throughout, so the next full raise is always to the current bet
    plus 100. The small blind acted at 100 and now faces 100 more, a full raise in total, so it may raise to at least
    300; it calls. UTG acted at 160 and faces only 40 more, so it may only call or fold."""
    h = checked(make_hand({5: 300, 8: 1000, 1: 260, 3: 1000}, button_seat_number=FOUR_HANDED_BUTTON))
    h.start(STAKES)
    h.act((3, CALL), (5, CALL), (8, CALL), (1, CHECK))
    h.next_street()

    h.act((8, bet(100)), (1, raise_to(160)))
    assert (h.betting.current_bet, h.betting.last_full_raise_size) == (160, 100)
    assert (h.betting.current_actor, h.betting.pending_actors) == (3, {3, 5, 8})
    h.act((3, CALL))
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

    assert (h.betting.current_actor, h.betting.pending_actors) == (8, {8, 3})
    assert legal_actions(h.hand) == legal(
        can_call=True, amount_owed=100, call_amount=100, can_raise=True, min_full_target=300, max_target=900
    )
    h.act((8, CALL))
    assert (h.betting.current_actor, h.betting.pending_actors) == (3, {3})
    assert legal_actions(h.hand) == legal(can_call=True, amount_owed=40, call_amount=40)
    h.act((3, CALL))

    assert is_round_complete(h.betting)
    assert totals(h) == {5: 300, 8: 300, 1: 260, 3: 300}
    assert pots(h.hand) == (pot(1040, 5, 8, 1, 3), pot(120, 5, 8, 3))


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
    assert totals(h) == {1: 130, 2: 130, 3: 130}


# =============================================================================
# SHORT BLINDS
# =============================================================================


def test_short_big_blind_multiway_keeps_the_nominal_big_blind_and_is_never_pending(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """Four-handed, the big blind is all-in for 30 of the 100 blind. The others still owe the full 100 and the minimum
    raise is to 200; UTG calls, the button raises to 300, the small blind folds and UTG calls. The big blind never
    owes an action and is eligible only for the main pot its 30 reach, and on the flop UTG is the first player able to
    act."""
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
    assert totals(h) == {5: 300, 8: 50, 1: 30, 3: 300}
    assert pots(h.hand) == (pot(120, 5, 1, 3), pot(60, 5, 3), pot(500, 5, 3))

    h.next_street()
    assert (h.betting.current_actor, h.betting.pending_actors) == (3, {3, 5})
    h.act((3, CHECK), (5, CHECK))
    assert is_round_complete(h.betting)


@pytest.mark.parametrize(
    "blind_chips, posted, pending, owed, matched",
    [
        pytest.param({2: 30}, {2: 30, 3: 100}, {1, 3}, 0, 30, id="short-small-blind"),
        pytest.param({3: 30}, {2: 50, 3: 30}, {1, 2}, 0, 30, id="big-blind-below-the-small-blind"),
        pytest.param({3: 70}, {2: 50, 3: 70}, {1, 2}, 20, 70, id="big-blind-between-the-blinds"),
        pytest.param({3: 100}, {2: 50, 3: 100}, {1, 2}, 50, 100, id="big-blind-of-exactly-the-whole-stack"),
    ],
)
def test_all_in_blind_keeps_the_nominal_big_blind_and_is_called_for_what_it_can_contest(
    blind_chips: dict[int, int],
    posted: dict[int, int],
    pending: set[int],
    owed: int,
    matched: int,
    checked: Callable[[PokerHand], CheckedHand],
    make_hand: HandFactory,
) -> None:
    """Three-handed, one blind posts its whole stack and is all-in: a short small blind of 30, a big blind of 30
    (below the small blind), a big blind of 70 (between the blinds), or a big blind of exactly 100. The current bet
    and the last full raise size stay at the full big blind, and the all-in blind never owes an action. While the
    other blind can still respond, the button owes the nominal 100 and may raise to 200; it folds. The other blind is
    then the only player who can act, and it owes only what the all-in blind can contest: the difference, which it
    calls, or nothing when it already has as much in front. In that case the round completes as soon as the button
    folds, a big blind with chips gets no option because nobody could respond, and the other blind's unmatched chips
    go back. Either way both blinds end with the same total in one pot."""
    starting_chips = {1: 1000, 2: 1000, 3: 1000} | blind_chips
    h = checked(make_hand(starting_chips, button_seat_number=THREE_HANDED_BUTTON))
    h.start(STAKES)
    assert in_front(h) == {1: 0} | posted
    assert {seat for seat, hp in h.seats.items() if hp.all_in} == set(blind_chips)
    assert (h.betting.current_bet, h.betting.last_full_raise_size) == (100, 100)
    assert (h.betting.current_actor, h.betting.pending_actors) == (1, pending)
    assert legal_actions(h.hand) == legal(
        can_call=True, amount_owed=100, call_amount=100, can_raise=True, min_full_target=200, max_target=1000
    )

    h.act((1, FOLD))
    if owed:
        assert (h.betting.current_actor, h.betting.pending_actors) == (2, {2})
        assert legal_actions(h.hand) == legal(can_call=True, amount_owed=owed, call_amount=owed)
        h.act((2, CALL))
    else:
        assert (h.betting.current_actor, h.betting.pending_actors) == (None, set())

    assert is_round_complete(h.betting)
    assert is_betting_closed(h.hand)
    assert h.betting.current_bet == 100
    assert stacks(h) == {1: 1000, 2: starting_chips[2] - matched, 3: starting_chips[3] - matched}
    assert totals(h) == {1: 0, 2: matched, 3: matched}
    assert pots(h.hand) == (pot(2 * matched, 2, 3),)


def test_heads_up_short_big_blind_is_called_for_what_it_can_contest(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """Heads-up, the big blind is all-in for 70 of the 100 blind. The small blind, with 50 in, owes only 20, not the
    nominal 50 more: it calls 20, so both have committed 70 and the collection returns nothing and moves 140 into the
    middle. The current bet stays 100 and no further betting is possible. Every later round starts complete."""
    h = checked(make_hand({3: 70, 7: 1000}, button_seat_number=7))
    h.start(STAKES)
    assert (h.betting.current_actor, h.betting.pending_actors) == (7, {7})

    assert legal_actions(h.hand) == legal(can_call=True, amount_owed=20, call_amount=20)
    h.act((7, CALL))

    assert in_front(h) == {7: 0, 3: 0}
    assert stacks(h) == {7: 930, 3: 0}
    assert pots(h.hand) == (pot(140, 7, 3),)
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
    to 400 and the others call. On the flop, turn and river the deeper players keep betting and raising, and the
    small blind folds on the flop; UTG is never pending or to act again. Each street's betting grows only the side
    pots: UTG stays eligible for the main pot its 150 reach, of 600, and for no side pot, while the folded small
    blind's chips stay in both pots they reached and it is eligible for none. On the river two players can still act,
    so betting is not closed even with the round complete."""
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
    assert totals(h) == {5: 400, 8: 400, 1: 400, 3: 150}
    assert middle_pot(h.hand) == 1350
    assert pots(h.hand) == (pot(600, 5, 8, 1, 3), pot(750, 5, 8, 1))

    h.next_street()
    assert (h.betting.current_actor, h.betting.pending_actors) == (8, {8, 1, 5})
    h.act((8, CHECK), (1, bet(300)), (5, raise_to(900)), (8, FOLD), (1, CALL))
    assert totals(h) == {5: 1300, 8: 400, 1: 1300, 3: 150}
    assert middle_pot(h.hand) == 3150
    assert pots(h.hand) == (pot(600, 5, 1, 3), pot(750, 5, 1), pot(1800, 5, 1))

    h.next_street()
    assert (h.betting.current_actor, h.betting.pending_actors) == (1, {1, 5})
    h.act((1, CHECK), (5, bet(500)), (1, CALL))
    assert middle_pot(h.hand) == 4150
    turn_pots = (pot(600, 5, 1, 3), pot(750, 5, 1), pot(2800, 5, 1))
    assert pots(h.hand) == turn_pots

    h.next_street()
    assert (h.betting.current_actor, h.betting.pending_actors) == (1, {1, 5})
    h.act((1, CHECK), (5, CHECK))

    assert is_round_complete(h.betting)
    assert not is_betting_closed(h.hand)
    assert totals(h) == {5: 1800, 8: 400, 1: 1800, 3: 150}
    assert stacks(h) == {5: 200, 8: 1600, 1: 200, 3: 0}
    assert pots(h.hand) == turn_pots


# =============================================================================
# CHIPS IN FRONT AND THE MIDDLE POT
# =============================================================================


@pytest.mark.parametrize(
    "big_blind_chips, called_in_front, returned, middle_after, pots_after",
    [
        pytest.param(1000, 100, 0, 500, (pot(300, 2, 3), pot(200, 2, 3)), id="matched-call"),
        pytest.param(170, 70, 30, 440, (pot(300, 2, 3), pot(140, 2, 3)), id="short-all-in-call"),
    ],
)
def test_chips_in_front_join_the_middle_pot_only_when_their_round_is_collected(
    big_blind_chips: int,
    called_in_front: int,
    returned: int,
    middle_after: int,
    pots_after: tuple[Pot, ...],
    checked: Callable[[PokerHand], CheckedHand],
    make_hand: HandFactory,
) -> None:
    """Called around preflop, the middle pot holds 300 on the flop. The small blind, with 500 behind, bets 100: its
    stack drops to 400 and the 100 sit in front of it, outside the middle pot. The big blind calls, either the full
    100 or all-in for its last 70, and both stay in front while the button still has to act. Once the button folds,
    the round is collected: the 30 of the bet that the short call could not match go back to the small blind, nothing
    is left in front, and the matched chips join the middle pot (300 + 200, or 300 + 140)."""
    h = called_around_to_the_flop(
        checked, make_hand({1: 1000, 2: 600, 3: big_blind_chips}, button_seat_number=THREE_HANDED_BUTTON)
    )
    assert (middle_pot(h.hand), pots(h.hand)) == (300, (pot(300, 1, 2, 3),))

    h.act((2, bet(100)))
    assert (stacks(h)[2], in_front(h)[2], middle_pot(h.hand)) == (400, 100, 300)

    h.act((3, CALL))
    assert in_front(h) == {1: 0, 2: 100, 3: called_in_front}
    assert middle_pot(h.hand) == 300

    h.act((1, FOLD))
    assert in_front(h) == {1: 0, 2: 0, 3: 0}
    assert stacks(h)[2] == 400 + returned
    assert middle_pot(h.hand) == middle_after
    assert pots(h.hand) == pots_after


# =============================================================================
# POTS
# =============================================================================


def test_folded_chips_stay_in_every_pot_they_reached_while_all_in_players_stay_eligible(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """Four-handed: UTG is all-in for 150 preflop, and the button calls all-in for 400 after the big blind's raise. The
    blinds keep betting on the flop; on the turn the big blind raises all-in to 1300 and the small blind, the only
    player left who can act, owes 800 more, all it has, and folds after putting 1200 into the hand. Its chips stay in
    all three pots they reached, but it is eligible for none, while each all-in player stays eligible for every pot it
    reaches. The big blind's 800 above the small blind's folded 1200 are uncalled and go back to it at the collection
    (measured against the button's 400, the largest live contribution, it would be 1600), so it has chips again and is
    no longer all-in. Only the contested chips are collected: 500 from each blind, so the middle pot grows from 1950
    to 2950, and the top pot is the small blind's dead 800 plus the big blind's matching 800."""
    h = checked(make_hand({5: 400, 8: 2000, 1: 2000, 3: 150}, button_seat_number=FOUR_HANDED_BUTTON))
    h.start(STAKES)
    h.act((3, raise_to(150)), (5, CALL), (8, CALL), (1, raise_to(400)), (5, CALL), (8, CALL))
    assert totals(h) == {5: 400, 8: 400, 1: 400, 3: 150}
    assert pots(h.hand) == (pot(600, 5, 8, 1, 3), pot(750, 5, 8, 1))

    h.next_street()
    h.act((8, bet(300)), (1, CALL))
    assert pots(h.hand) == (pot(600, 5, 8, 1, 3), pot(750, 5, 8, 1), pot(600, 8, 1))

    h.next_street()
    h.act((8, bet(500)), (1, raise_to(1300)))
    assert (stacks(h)[1], h.seats[1].all_in) == (0, True)
    assert in_front(h) == {5: 0, 8: 500, 1: 1300, 3: 0}
    assert middle_pot(h.hand) == 1950
    assert legal_actions(h.hand) == legal(can_call=True, amount_owed=800, call_amount=800, call_is_all_in=True)
    h.act((8, FOLD))

    assert in_front(h) == {5: 0, 8: 0, 1: 0, 3: 0}
    assert totals(h) == {5: 400, 8: 1200, 1: 1200, 3: 150}
    assert stacks(h) == {5: 0, 8: 800, 1: 800, 3: 0}
    assert (h.seats[1].all_in, h.seats[8].folded) == (False, True)
    assert middle_pot(h.hand) == 2950
    assert pots(h.hand) == (pot(600, 5, 1, 3), pot(750, 5, 1), pot(1600, 1))
    assert is_betting_closed(h.hand)
