"""The settled-hand guard: every public hand-level mutation entry point rejects a settled hand first.

Settled hands are built through public operations only, from a deck stacked by the shared `stacked_hand` fixture. The
three seats are the button (1), the small blind (2) and the big blind (3); preflop seat 1 acts first and on every later
street seat 2 does. Each rejection is `HandAlreadySettledError` and leaves the whole hand unchanged. The guard is a
check on the hand's settlement marker, not immutability, so only the hand itself is compared.
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest

import go_poker.game.poker_hand as poker_hand_module
import go_poker.game.settlement as settlement_module
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.legal_actions import NOTHING_LEGAL, legal_actions
from go_poker.game.betting.pots import middle_pot, pots
from go_poker.game.betting.rounds import start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.poker_hand import PokerHand
from go_poker.game.settlement import HandAlreadySettledError
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.showdown import reveal_hands, settle_hand

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)

HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
BOARD = "2c 7d 9h Jc Ks"
TYING_HOLES = {1: "2c 3d", 2: "4h 5c", 3: "6d 7h"}  # all three play the royal flush on the board
ROYAL_FLUSH_BOARD = "As Ks Qs Js Ts"

type StackedHand = Callable[..., PokerHand]
type Operation = Callable[[PokerHand], None]


def snapshot(hand: PokerHand) -> dict[str, Any]:
    """Everything about the hand, for comparing before and after (the deck by its size: drawing is its only change)."""
    return {
        "street": hand.street,
        "board": list(hand.board),
        "burned": list(hand.burned_cards),
        "deck": len(hand.deck),
        "betting": copy.deepcopy(hand.betting),
        "settlement": hand.settlement,
        "reveal": hand.reveal,
        "players": [
            (
                state.seat_number,
                state.player.stack,
                state.folded,
                state.all_in,
                state.street_contribution,
                state.total_contribution,
                list(state.hole_cards),
            )
            for state in hand.players
        ],
        "pots": pots(hand),
        "middle_pot": middle_pot(hand),
    }


def assert_rejected(hand: PokerHand, operation: Operation) -> None:
    """The operation is rejected as settled and the hand is exactly as it was."""
    assert hand.settlement is not None
    before = snapshot(hand)

    with pytest.raises(HandAlreadySettledError):
        operation(hand)

    assert snapshot(hand) == before
    assert hand.settlement is before["settlement"]
    assert hand.reveal is before["reveal"]


def play(hand: PokerHand, *actions: tuple[int, Action]) -> None:
    for seat, action in actions:
        apply_action(hand, seat, action)


def next_street(hand: PokerHand) -> None:
    """Deal the next street, then start its betting round."""
    deal_next_street(hand)
    start_betting_round(hand)


def check_street(hand: PokerHand) -> None:
    """Everyone still to act checks, in turn."""
    assert hand.betting is not None
    while hand.betting.current_actor is not None:
        apply_action(hand, hand.betting.current_actor, CHECK)


def dealt_hand(
    stacked_hand: StackedHand,
    stacks: dict[int, int] | None = None,
    holes: dict[int, str] | None = None,
    board: str = BOARD,
) -> PokerHand:
    """A stacked hand with its blinds posted and hole cards dealt."""
    hand = stacked_hand(holes or HOLES, board, stacks=stacks)
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    return hand


def won_uncontested_on(stacked_hand: StackedHand, street: Street) -> PokerHand:
    """A hand with hole cards dealt that seat 2 wins uncontested on `street`, then settled."""
    hand = dealt_hand(stacked_hand)
    if street is Street.PREFLOP:
        play(hand, (1, FOLD), (2, FOLD))
    else:
        play(hand, (1, CALL), (2, CALL), (3, CHECK))
        while hand.street is not street:
            next_street(hand)
            if hand.street is street:
                play(hand, (2, Action(ActionType.BET, 10)), (3, FOLD), (1, FOLD))
            else:
                check_street(hand)
    settle_hand(hand)
    return hand


def folded_out_before_hole_cards(stacked_hand: StackedHand) -> PokerHand:
    """Blinds posted, seats 1 and 2 fold to the big blind before any hole card is dealt, then settled."""
    hand = stacked_hand(HOLES, BOARD)
    initialize_betting(hand, STAKES)
    play(hand, (1, FOLD), (2, FOLD))
    settle_hand(hand)
    assert not any(state.hole_cards for state in hand.players)
    return hand


def all_in_runout(stacked_hand: StackedHand, holes: dict[int, str], board: str) -> PokerHand:
    """Everyone all-in preflop, the whole board dealt without starting later rounds, then settled."""
    hand = dealt_hand(stacked_hand, stacks={1: 100, 2: 100, 3: 100}, holes=holes, board=board)
    play(hand, (1, Action(ActionType.RAISE, 100)), (2, CALL), (3, CALL))
    while hand.street is not Street.RIVER:
        deal_next_street(hand)
    settle_hand(hand)
    return hand


def side_pot_runout(stacked_hand: StackedHand) -> PokerHand:
    """Seat 2 is all-in short and wins the main pot with kings, seat 1 wins the side pot against seat 3 with aces, and
    seat 3 loses and stays all-in with no chips. After payout two seats have chips and are no longer all-in, so only
    the guard stops a new betting round from having players to act."""
    hand = dealt_hand(stacked_hand, stacks={1: 300, 2: 100, 3: 300})
    play(hand, (1, Action(ActionType.RAISE, 300)), (2, CALL), (3, CALL))
    while hand.street is not Street.RIVER:
        deal_next_street(hand)
    settle_hand(hand)
    paid = {state.seat_number: state.player.stack for state in hand.players}
    assert paid == {1: 400, 2: 300, 3: 0}
    assert [state.seat_number for state in hand.players if not state.all_in] == [1, 2]
    return hand


def heads_up_hand(stacked_hand: StackedHand) -> PokerHand:
    """Seat 1 is the button and small blind, seat 2 the big blind: seat 1 acts first preflop, seat 2 afterwards."""
    hand = stacked_hand({1: "Ah Ad", 2: "Kd Kh"}, BOARD)
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    assert hand.betting is not None
    assert hand.betting.current_actor == 1
    return hand


def heads_up_fold_on_flop(stacked_hand: StackedHand) -> PokerHand:
    hand = heads_up_hand(stacked_hand)
    play(hand, (1, CALL), (2, CHECK))
    next_street(hand)
    assert hand.betting is not None
    assert hand.betting.current_actor == 2
    play(hand, (2, Action(ActionType.BET, 10)), (1, FOLD))
    settle_hand(hand)
    return hand


def heads_up_all_in_runout(stacked_hand: StackedHand) -> PokerHand:
    hand = stacked_hand({1: "Ah Ad", 2: "Kd Kh"}, BOARD, stacks={1: 100, 2: 100})
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    play(hand, (1, Action(ActionType.RAISE, 100)), (2, CALL))
    while hand.street is not Street.RIVER:
        deal_next_street(hand)
    settle_hand(hand)
    return hand


def river_showdown(stacked_hand: StackedHand) -> PokerHand:
    """Checked down to the river and settled at showdown; the river round has been started."""
    hand = dealt_hand(stacked_hand)
    play(hand, (1, CALL), (2, CALL), (3, CHECK))
    while hand.street is not Street.RIVER:
        next_street(hand)
        check_street(hand)
    settle_hand(hand)
    return hand


# Every route to a settled hand: uncontested on each early street, contested by runout, and contested at the river.
SETTLED_HANDS: dict[str, Callable[[StackedHand], PokerHand]] = {
    "uncontested_before_hole_cards": folded_out_before_hole_cards,
    "uncontested_preflop": lambda stacked: won_uncontested_on(stacked, Street.PREFLOP),
    "uncontested_flop": lambda stacked: won_uncontested_on(stacked, Street.FLOP),
    "uncontested_turn": lambda stacked: won_uncontested_on(stacked, Street.TURN),
    "uncontested_river": lambda stacked: won_uncontested_on(stacked, Street.RIVER),
    "runout": lambda stacked: all_in_runout(stacked, HOLES, BOARD),
    "runout_split": lambda stacked: all_in_runout(stacked, TYING_HOLES, ROYAL_FLUSH_BOARD),
    "river_showdown": river_showdown,
    "side_pot_runout": side_pot_runout,
    "heads_up_uncontested_flop": heads_up_fold_on_flop,
    "heads_up_runout": heads_up_all_in_runout,
}

OPERATIONS: dict[str, Operation] = {
    "initialize_betting": lambda hand: initialize_betting(hand, STAKES),
    "deal_hole_cards": deal_hole_cards,
    "deal_next_street": deal_next_street,
    "start_betting_round": start_betting_round,
    "apply_action": lambda hand: apply_action(hand, 1, CHECK),
    "reveal_hands": reveal_hands,
    "settle_hand": settle_hand,
}


@pytest.fixture(params=SETTLED_HANDS)
def settled_hand(request: pytest.FixtureRequest, stacked_hand: StackedHand) -> PokerHand:
    hand: PokerHand = SETTLED_HANDS[request.param](stacked_hand)
    assert hand.settlement is not None
    return hand


@pytest.mark.parametrize("operation", OPERATIONS.values(), ids=OPERATIONS.keys())
def test_every_hand_mutation_entry_point_rejects_a_settled_hand(settled_hand: PokerHand, operation: Operation) -> None:
    assert_rejected(settled_hand, operation)


def test_derived_reads_stay_available_and_offer_nothing_on_a_settled_hand(settled_hand: PokerHand) -> None:
    """Reads are deliberately unguarded: nobody is to act on a settled hand and reading changes nothing."""
    before = snapshot(settled_hand)

    assert legal_actions(settled_hand) == NOTHING_LEGAL
    assert settled_hand.betting is not None
    assert settled_hand.betting.current_actor is None

    assert snapshot(settled_hand) == before


def test_the_error_is_the_same_class_from_settlement_and_poker_hand() -> None:
    assert settlement_module.HandAlreadySettledError is poker_hand_module.HandAlreadySettledError


# -----------------------------------------------------------------------------
# Operations that would otherwise succeed
# -----------------------------------------------------------------------------


def test_deal_hole_cards_is_rejected_for_a_hand_folded_out_before_hole_cards(stacked_hand: StackedHand) -> None:
    """Preflop, no hole cards and a full deck: unguarded this would deal cards to a settled hand."""
    hand = folded_out_before_hole_cards(stacked_hand)
    assert hand.street is Street.PREFLOP

    assert_rejected(hand, deal_hole_cards)


@pytest.mark.parametrize("street", [Street.PREFLOP, Street.FLOP, Street.TURN])
def test_deal_next_street_is_rejected_for_a_hand_won_uncontested(stacked_hand: StackedHand, street: Street) -> None:
    hand = won_uncontested_on(stacked_hand, street)
    assert hand.street is street

    assert_rejected(hand, deal_next_street)


@pytest.mark.parametrize(
    ("holes", "board"), [(HOLES, BOARD), (TYING_HOLES, ROYAL_FLUSH_BOARD)], ids=["one_winner", "split_pot"]
)
def test_start_betting_round_is_rejected_for_a_settled_all_in_runout(
    stacked_hand: StackedHand, holes: dict[int, str], board: str
) -> None:
    """The preflop round is complete and the river dealt without its round started; payout clears the paid seats'
    all_in, so unguarded a new round would start on the settled hand."""
    hand = all_in_runout(stacked_hand, holes, board)
    assert hand.betting is not None
    assert hand.betting.street is Street.PREFLOP
    assert hand.street is Street.RIVER

    assert_rejected(hand, start_betting_round)


def test_start_betting_round_is_rejected_for_a_settled_side_pot_runout(stacked_hand: StackedHand) -> None:
    hand = side_pot_runout(stacked_hand)
    assert hand.betting is not None
    assert hand.betting.street is Street.PREFLOP
    assert hand.street is Street.RIVER

    assert_rejected(hand, start_betting_round)


# -----------------------------------------------------------------------------
# The settled error wins over the error a settled hand would otherwise hit
# -----------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["uncontested_preflop", "river_showdown"])
def test_initialize_betting_reports_settled_over_already_initialized(stacked_hand: StackedHand, name: str) -> None:
    assert_rejected(SETTLED_HANDS[name](stacked_hand), OPERATIONS["initialize_betting"])


@pytest.mark.parametrize("seat", [1, 2, 3])
@pytest.mark.parametrize("name", ["uncontested_preflop", "uncontested_turn", "runout_split", "river_showdown"])
def test_apply_action_reports_settled_over_not_players_turn(stacked_hand: StackedHand, name: str, seat: int) -> None:
    """The round is complete, so nobody is to act; seat 1 is the natural preflop actor and seat 2 acts first on every
    later street."""
    hand = SETTLED_HANDS[name](stacked_hand)
    assert hand.betting is not None
    assert hand.betting.current_actor is None

    assert_rejected(hand, lambda settled: apply_action(settled, seat, CHECK))


def test_reveal_hands_reports_settled_over_already_revealed(stacked_hand: StackedHand) -> None:
    """The reveal was recorded before the settlement, so a second reveal would also be a double reveal."""
    hand = dealt_hand(stacked_hand, stacks={1: 100, 2: 100, 3: 100})
    play(hand, (1, Action(ActionType.RAISE, 100)), (2, CALL), (3, CALL))
    reveal_hands(hand)
    reveal = hand.reveal
    while hand.street is not Street.RIVER:
        deal_next_street(hand)
    settle_hand(hand)
    assert hand.reveal is reveal

    assert_rejected(hand, reveal_hands)


def test_deal_next_street_reports_settled_over_no_next_street(stacked_hand: StackedHand) -> None:
    hand = river_showdown(stacked_hand)
    assert hand.street is Street.RIVER

    assert_rejected(hand, deal_next_street)


def test_deal_hole_cards_reports_settled_over_hand_past_preflop(stacked_hand: StackedHand) -> None:
    hand = river_showdown(stacked_hand)
    assert hand.street is not Street.PREFLOP

    assert_rejected(hand, deal_hole_cards)


def test_deal_hole_cards_reports_settled_over_hole_cards_already_dealt(stacked_hand: StackedHand) -> None:
    hand = won_uncontested_on(stacked_hand, Street.PREFLOP)
    assert hand.street is Street.PREFLOP
    assert all(state.hole_cards for state in hand.players)

    assert_rejected(hand, deal_hole_cards)


def test_start_betting_round_reports_settled_over_round_already_started(stacked_hand: StackedHand) -> None:
    hand = river_showdown(stacked_hand)
    assert hand.betting is not None
    assert hand.betting.street is hand.street

    assert_rejected(hand, start_betting_round)
