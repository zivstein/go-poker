"""Milestone 3 multi-level all-in and side-pot scenarios driven through the public dealing and betting operations.

Hands are built the way hand setup builds them (the conftest `make_hand`) at blinds 50/100. Every step re-checks the
betting and accounting invariants (see `CheckedHand.check` in the conftest). These scenarios prove how all-ins at many
levels, on one street or across several, a fold after funding several layers, and a call against several all-in
opponents shape the collected contributions, the middle pot, and the main and side pots with their eligible seats.
"""

from collections.abc import Callable
from typing import Any

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


FOUR_HANDED_BUTTON = 5  # seats 5 (button), 8 (small blind), 1 (big blind), 3 (UTG); seat 8 acts first after the flop
# Seats 1 to 9 clockwise from button seat 1: seat 2 is the small blind, seat 3 the big blind, seat 4 acts first
# preflop, and seat 2 first after the flop.
SEAT_ONE_BUTTON = 1


# =============================================================================
# MANY ALL-IN LEVELS ON ONE STREET
# =============================================================================


def test_nine_players_all_in_preflop_at_nine_levels_make_a_main_pot_and_seven_side_pots(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """Nine-handed, every player ends up all-in preflop with a different stack:

    | Seat | Stack | Action                         | Committed | After collection |
    | ---- | ----- | ------------------------------ | --------- | ---------------- |
    | 4    | 250   | raises all-in to 250 (full)    | 250       | 250              |
    | 5    | 330   | raises all-in to 330 (short)   | 330       | 330              |
    | 6    | 2000  | raises all-in to 2000 (full)   | 2000      | 1400, 600 back   |
    | 7    | 120   | calls all-in for 120           | 120       | 120              |
    | 8    | 900   | calls all-in for 900           | 900       | 900              |
    | 9    | 600   | calls all-in for 600           | 600       | 600              |
    | 1    | 1400  | calls all-in for 1400 (button) | 1400      | 1400             |
    | 2    | 470   | calls all-in for 470 (SB)      | 470       | 470              |
    | 3    | 1100  | calls all-in for 1100 (BB)     | 1100      | 1100             |

    The big blind is last and every opponent is all-in, so it owes the 1900 that seat 6's 2000 contest and calls its
    last 1000. Nine distinct levels are committed, but nobody matches seat 6's 600 above the button's 1400, so they go
    back to seat 6 at the collection instead of forming a one-contributor ninth pot. The eight remaining levels make a
    main pot and seven side pots, each contested by the players whose contribution reaches it, and no further betting
    is possible: the later rounds ask nobody to act."""
    h = checked(
        make_hand(
            {1: 1400, 2: 470, 3: 1100, 4: 250, 5: 330, 6: 2000, 7: 120, 8: 900, 9: 600},
            button_seat_number=SEAT_ONE_BUTTON,
        )
    )
    h.start(STAKES)
    h.act((4, raise_to(250)), (5, raise_to(330)), (6, raise_to(2000)))
    assert (h.betting.current_bet, h.betting.last_full_raise_size) == (2000, 1670)
    h.act((7, CALL), (8, CALL), (9, CALL), (1, CALL), (2, CALL))

    assert (h.betting.current_actor, h.betting.pending_actors) == (3, {3})
    assert legal_actions(h.hand) == legal(can_call=True, amount_owed=1900, call_amount=1000, call_is_all_in=True)
    h.act((3, CALL))

    assert is_round_complete(h.betting)
    assert is_betting_closed(h.hand)
    assert in_front(h) == {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0}
    assert stacks(h) == {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 600, 7: 0, 8: 0, 9: 0}
    assert totals(h) == {1: 1400, 2: 470, 3: 1100, 4: 250, 5: 330, 6: 1400, 7: 120, 8: 900, 9: 600}
    assert middle_pot(h.hand) == 6570
    expected_pots = (
        pot(1080, 1, 2, 3, 4, 5, 6, 7, 8, 9),  # main pot: 9 x 120
        pot(1040, 1, 2, 3, 4, 5, 6, 8, 9),  # 8 x 130, from 120 to 250
        pot(560, 1, 2, 3, 5, 6, 8, 9),  # 7 x 80, from 250 to 330
        pot(840, 1, 2, 3, 6, 8, 9),  # 6 x 140, from 330 to 470
        pot(650, 1, 3, 6, 8, 9),  # 5 x 130, from 470 to 600
        pot(1200, 1, 3, 6, 8),  # 4 x 300, from 600 to 900
        pot(600, 1, 3, 6),  # 3 x 200, from 900 to 1100
        pot(600, 1, 6),  # 2 x 300, from 1100 to 1400
    )
    assert pots(h.hand) == expected_pots

    for street in (Street.FLOP, Street.TURN, Street.RIVER):
        h.next_street()
        assert (h.betting.street, h.betting.current_actor, h.betting.pending_actors) == (street, None, set())
        assert pots(h.hand) == expected_pots


# =============================================================================
# ALL-INS ACROSS STREETS
# =============================================================================


def test_all_ins_on_successive_streets_give_each_pot_its_own_eligible_seats(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """Four-handed: UTG (A) is all-in preflop, the small blind (B) on the flop, and the big blind (C) on the turn,
    while the button (D) covers everyone. Each completed round is collected, so the next starts with nothing in
    front, and each all-in adds a layer above the previous one:

    | After   | Totals A / B / C / D    | Middle | Pots (eligible seats)                                |
    | ------- | ----------------------- | ------ | ---------------------------------------------------- |
    | preflop | 300 / 300 / 300 / 300   | 1200   | 1200 (A B C D)                                       |
    | flop    | 300 / 800 / 1500 / 1500 | 4100   | 1200 (A B C D), 1500 (B C D), 1400 (C D)             |
    | turn    | 300 / 800 / 2000 / 2000 | 5100   | 1200 (A B C D), 1500 (B C D), 2400 (C D)             |

    A can win only the main pot, B also the first side pot, and C and D every pot. On the turn the big blind's bet and
    the button's raise stay in front of them, outside the middle pot, and the big blind owes the raise minus the 200
    it already has in front, more than its last 300: its short call goes all-in, the button's 300 that it cannot match
    go back, and the matched chips join the middle. Then nobody can bet any more."""
    a, b, c, d = 3, 8, 1, 5
    h = checked(make_hand({d: 3000, b: 800, c: 2000, a: 300}, button_seat_number=FOUR_HANDED_BUTTON))
    h.start(STAKES)

    # Preflop: A raises all-in, and everyone calls.
    h.act((a, raise_to(300)), (d, CALL), (b, CALL), (c, CALL))
    assert is_round_complete(h.betting)
    assert in_front(h) == {d: 0, b: 0, c: 0, a: 0}
    assert totals(h) == {d: 300, b: 300, c: 300, a: 300}
    assert middle_pot(h.hand) == 1200
    assert pots(h.hand) == (pot(1200, a, b, c, d),)

    # Flop: B bets all-in; C raises and D calls. The bet waits in front of B, outside the middle pot and the pots.
    h.next_street()
    assert (h.betting.current_actor, h.betting.pending_actors) == (b, {b, c, d})
    h.act((b, bet(500)))
    assert (stacks(h)[b], in_front(h)[b], middle_pot(h.hand)) == (0, 500, 1200)
    assert pots(h.hand) == (pot(1200, a, b, c, d),)
    h.act((c, raise_to(1200)), (d, CALL))
    assert is_round_complete(h.betting)
    assert in_front(h) == {d: 0, b: 0, c: 0, a: 0}
    assert totals(h) == {d: 1500, b: 800, c: 1500, a: 300}
    assert middle_pot(h.hand) == 4100
    assert pots(h.hand) == (pot(1200, a, b, c, d), pot(1500, b, c, d), pot(1400, c, d))

    # Turn: C bets, D raises, and C's call is short and all-in.
    h.next_street()
    assert (h.betting.current_actor, h.betting.pending_actors) == (c, {c, d})
    assert (stacks(h)[c], stacks(h)[d], middle_pot(h.hand)) == (500, 1500, 4100)

    h.act((c, bet(200)))
    assert (stacks(h)[c], in_front(h)[c], middle_pot(h.hand)) == (300, 200, 4100)
    assert legal_actions(h.hand) == legal(
        can_call=True, amount_owed=200, call_amount=200, can_raise=True, min_full_target=400, max_target=1500
    )

    h.act((d, raise_to(800)))
    assert (stacks(h)[d], in_front(h)[d], middle_pot(h.hand)) == (700, 800, 4100)
    assert legal_actions(h.hand) == legal(can_call=True, amount_owed=600, call_amount=300, call_is_all_in=True)

    h.act((c, CALL))
    assert is_round_complete(h.betting)
    assert is_betting_closed(h.hand)
    assert in_front(h) == {d: 0, b: 0, c: 0, a: 0}
    assert stacks(h) == {d: 1000, b: 0, c: 0, a: 0}
    assert totals(h) == {d: 2000, b: 800, c: 2000, a: 300}
    assert middle_pot(h.hand) == 5100
    turn_pots = (pot(1200, a, b, c, d), pot(1500, b, c, d), pot(2400, c, d))
    assert pots(h.hand) == turn_pots

    # River: D is the only player who can still bet, so the round asks nobody to act.
    h.next_street()
    assert (h.betting.current_actor, h.betting.pending_actors) == (None, set())
    assert pots(h.hand) == turn_pots


# =============================================================================
# A FOLD AFTER FUNDING SEVERAL LAYERS
# =============================================================================


def test_fold_after_funding_three_layers_keeps_the_chips_in_them_but_leaves_every_eligible_set(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """Five-handed: UTG (A) is all-in for 200 preflop and the small blind (B) for 700 on the flop, where the big blind
    (F) raises and the button (D) and the cutoff (C) call. Before the turn F contests all three pots. On the turn F
    bets 300, C raises to 800, D calls, and F folds instead of calling. None of F's 1500 come back, its 300 turn bet
    included: they stay in every pot they reach as dead money, while F leaves every eligible set. A and B stay
    eligible for the pots their all-ins reach, the second side pot is now contested only by C and D, and F's folded
    1500 still mark a layer boundary, so the last two pots stay separate although C and D are eligible for both."""
    d, b, f, a, c = 1, 2, 3, 4, 5
    h = checked(make_hand({d: 3000, b: 700, f: 3000, a: 200, c: 3000}, button_seat_number=SEAT_ONE_BUTTON))
    h.start(STAKES)
    h.act((a, raise_to(200)), (c, CALL), (d, CALL), (b, CALL), (f, CALL))
    assert pots(h.hand) == (pot(1000, d, b, f, a, c),)

    h.next_street()
    h.act((b, bet(500)), (f, raise_to(1000)), (c, CALL), (d, CALL))
    assert totals(h) == {d: 1200, b: 700, f: 1200, a: 200, c: 1200}
    assert pots(h.hand) == (pot(1000, d, b, f, a, c), pot(2000, d, b, f, c), pot(1500, d, f, c))

    h.next_street()
    h.act((f, bet(300)), (c, raise_to(800)), (d, CALL))
    assert in_front(h) == {d: 800, b: 0, f: 300, a: 0, c: 800}
    assert middle_pot(h.hand) == 4500
    assert pots(h.hand) == (pot(1000, d, b, f, a, c), pot(2000, d, b, f, c), pot(1500, d, f, c))

    h.act((f, FOLD))
    assert is_round_complete(h.betting)
    assert not is_betting_closed(h.hand)  # C and D can still bet on the river
    assert (stacks(h)[f], totals(h)[f]) == (1500, 1500)
    assert in_front(h) == {d: 0, b: 0, f: 0, a: 0, c: 0}
    assert totals(h) == {d: 2000, b: 700, f: 1500, a: 200, c: 2000}
    assert middle_pot(h.hand) == 6400
    assert pots(h.hand) == (
        pot(1000, d, b, a, c),  # 5 x 200
        pot(2000, d, b, c),  # 4 x 500, from 200 to 700
        pot(2400, d, c),  # 3 x 800, from 700 to F's folded 1500
        pot(1000, d, c),  # 2 x 500, from 1500 to 2000
    )


# =============================================================================
# CALLING SEVERAL ALL-IN OPPONENTS
# =============================================================================


def test_last_player_able_to_act_owes_the_largest_all_in_not_the_smallest_or_the_nominal_bet(
    checked: Callable[[PokerHand], CheckedHand], make_hand: HandFactory
) -> None:
    """Five-handed: the big blind is all-in for 60 of the 100 blind, and UTG and the cutoff call all-in for 80 and 90,
    so nobody has matched the nominal 100. While the button can still respond, it owes the full 100; it folds. The
    small blind, with 50 in front, is then the only player who can act, and every opponent is all-in: it owes the 40
    that the largest of them, the cutoff's 90, can contest, not the 10 to the smallest all-in nor the 50 to the
    nominal current bet, which stays 100. Its call completes the round with nothing returned, and the three all-in
    levels make three pots."""
    btn, sb, bb, utg, co = 1, 2, 3, 4, 5
    h = checked(make_hand({btn: 1000, sb: 1000, bb: 60, utg: 80, co: 90}, button_seat_number=SEAT_ONE_BUTTON))
    h.start(STAKES)
    assert (h.betting.current_actor, h.betting.pending_actors) == (utg, {utg, co, btn, sb})

    assert legal_actions(h.hand) == legal(can_call=True, amount_owed=100, call_amount=80, call_is_all_in=True)
    h.act((utg, CALL), (co, CALL))
    assert legal_actions(h.hand) == legal(
        can_call=True, amount_owed=100, call_amount=100, can_raise=True, min_full_target=200, max_target=1000
    )
    h.act((btn, FOLD))

    assert in_front(h) == {btn: 0, sb: 50, bb: 60, utg: 80, co: 90}
    assert (h.betting.current_actor, h.betting.pending_actors) == (sb, {sb})
    assert legal_actions(h.hand) == legal(can_call=True, amount_owed=40, call_amount=40)
    h.act((sb, CALL))

    assert is_round_complete(h.betting)
    assert is_betting_closed(h.hand)
    assert h.betting.current_bet == 100
    assert stacks(h) == {btn: 1000, sb: 910, bb: 0, utg: 0, co: 0}
    assert totals(h) == {btn: 0, sb: 90, bb: 60, utg: 80, co: 90}
    assert middle_pot(h.hand) == 320
    assert pots(h.hand) == (pot(240, sb, bb, utg, co), pot(60, sb, utg, co), pot(20, sb, co))
