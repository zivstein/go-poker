"""The river decision order across seat layouts, buttons, folds and aggressors, through the public operations.

The expected order is stated from the ring of seats alone: the live seats clockwise (ascending seat numbers, wrapping),
starting with the first seat left of the button and ending with the button, rotated to start at the river's last bettor
when somebody bet. It never reads the engine's order helper or `BettingState.last_aggressor`. Every layout uses
non-consecutive seat numbers, so a mistake that treats seat numbers as consecutive positions fails here.

Each hand is checked down to the river (optionally with the first preflop actor folding), played through its river round
with the chosen bettor, and then every decider in turn shows; the decisions must be accepted exactly in the expected
order and the hand then settles with chips conserved.
"""

from collections.abc import Callable

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.legal_actions import legal_actions
from go_poker.game.betting.rounds import start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.poker_hand import PokerHand
from go_poker.game.showdown import NotShowdownTurnError, ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.showdown import apply_showdown_action, settle_hand, start_showdown

STAKES = Stakes(small_blind=5, big_blind=10)
BOARD = "2c 7d 9h Jc Ks"
HOLE_POOL = ["Ah Ad", "Kd Kh", "3s 4s", "Qs Qc"]
LAYOUTS = [(3, 8), (2, 5, 7, 9), (1, 4, 6), (4, 5, 6, 9)]
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
FOLD = Action(ActionType.FOLD)

type NewHand = Callable[..., PokerHand]


def expected_order(seats: tuple[int, ...], button: int, live: set[int], bettor: int | None) -> list[int]:
    """The live seats clockwise from the seat left of the button, the button last, rotated to start at the bettor."""
    ring = sorted(seats)
    after_button = [seat for seat in ring if seat > button] + [seat for seat in ring if seat < button]
    clockwise = [seat for seat in (*after_button, button) if seat in live]
    start = clockwise.index(bettor) if bettor is not None else 0
    return clockwise[start:] + clockwise[:start]


def play_to_river_showdown(
    stacked_hand: NewHand, seats: tuple[int, ...], button: int, fold_first_actor: bool, bettor_choice: int | None
) -> tuple[PokerHand, set[int], int | None]:
    """Play the hand to a completed river round; return it, its live seats and the seat that bet on the river.

    `bettor_choice` indexes the live seats in ascending order (None: nobody bets)."""
    hand = stacked_hand(dict(zip(seats, HOLE_POOL, strict=False)), BOARD, button=button)
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    assert hand.betting is not None
    folded_first = False
    while hand.betting.current_actor is not None:
        actor = hand.betting.current_actor
        if fold_first_actor and not folded_first:
            apply_action(hand, actor, FOLD)
            folded_first = True
        else:
            apply_action(hand, actor, CHECK if legal_actions(hand).can_check else CALL)
    for _ in range(3):
        deal_next_street(hand)
        start_betting_round(hand)
        if hand.street is not Street.RIVER:
            while hand.betting.current_actor is not None:
                apply_action(hand, hand.betting.current_actor, CHECK)
    live = {state.seat_number for state in hand.players if not state.folded}
    bettor = sorted(live)[bettor_choice] if bettor_choice is not None else None
    bet_made = False
    while hand.betting.current_actor is not None:
        actor = hand.betting.current_actor
        if actor == bettor and not bet_made:
            apply_action(hand, actor, Action(ActionType.BET, 30))
            bet_made = True
        else:
            apply_action(hand, actor, CALL if legal_actions(hand).can_call else CHECK)
    assert bet_made == (bettor is not None)
    return hand, live, bettor


CASES = [
    (layout, fold_first_actor, bettor_choice)
    for layout in LAYOUTS
    for fold_first_actor in (False, True)
    if not (fold_first_actor and len(layout) == 2)  # heads-up, a fold ends the hand before the river
    for bettor_choice in (None, *range(len(layout) - fold_first_actor))
]


@pytest.mark.parametrize(
    ("layout", "fold_first_actor", "bettor_choice"),
    CASES,
    ids=[
        "-".join(map(str, layout))
        + ("-fold" if fold else "-nofold")
        + ("-nobet" if bettor is None else f"-bettor{bettor}")
        for layout, fold, bettor in CASES
    ],
)
def test_the_decision_order_is_the_live_ring_from_the_seat_left_of_the_button_rotated_to_the_river_bettor(
    stacked_hand: NewHand, layout: tuple[int, ...], fold_first_actor: bool, bettor_choice: int | None
) -> None:
    for button in layout:
        hand, live, bettor = play_to_river_showdown(stacked_hand, layout, button, fold_first_actor, bettor_choice)
        order = expected_order(layout, button, live, bettor)
        starting_chips = sum(state.player.stack + state.total_contribution for state in hand.players)

        start_showdown(hand)

        showdown = hand.showdown
        assert showdown is not None and showdown.kind is ShowdownKind.INTERACTIVE
        assert list(showdown.order) == order, (layout, button, fold_first_actor, bettor)
        for position, seat in enumerate(order):
            assert hand.showdown is not None and hand.showdown.current_decider == seat
            for other in set(layout) - {seat}:
                with pytest.raises(NotShowdownTurnError):
                    apply_showdown_action(hand, other, ShowdownAction.SHOW)
            apply_showdown_action(hand, seat, ShowdownAction.SHOW)
            assert hand.showdown is not None and hand.showdown.decisions == (ShowdownAction.SHOW,) * (position + 1)
        assert hand.showdown is not None and hand.showdown.is_complete

        settle_hand(hand)

        assert hand.settlement is not None
        assert set(hand.settlement.payouts) <= live
        assert sum(state.player.stack for state in hand.players) == starting_chips
