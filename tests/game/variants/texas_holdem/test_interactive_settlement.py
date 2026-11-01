"""Hold'em settlement of an interactive river showdown: who is ranked, who competes and who is paid.

Every hand reaches its end through the real dealing, betting and showdown operations, from a deck stacked by the shared
`stacked_hand` fixture. Unless a test says otherwise the three seats are the button (1), the small blind (2) and the big
blind (3), all call preflop and check down to the river, and the decision order is seat 2, 3, 1; a river bet starts the
order with the last bettor or raiser.

On the default board 2c 7d 9h Jc Ks seat 2 holds a set of kings (the best hand), seat 1 a pair of aces and seat 3 only
king high. The `MUCKER_BEST_HOLES` give seat 1 a set of jacks, the best hand, ahead of seat 2's pair of aces.
"""

import copy
from collections.abc import Callable
from typing import Any

import pytest

import go_poker.game.variants.texas_holdem.showdown as showdown_module
from go_poker.core.card import Card
from go_poker.core.hand_rank import HandCategory, HandRank
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.pots import Pot, middle_pot, pots
from go_poker.game.betting.rounds import start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.hand_history import HandSettled
from go_poker.game.poker_hand import PokerHand
from go_poker.game.settlement import Settlement
from go_poker.game.showdown import Showdown, ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import InvalidHoleCardCountError, deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.showdown import (
    ShowdownIncompleteError,
    ShowdownNotReadyError,
    ShowdownNotStartedError,
    apply_showdown_action,
    settle_hand,
    start_showdown,
)

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
SHOW = ShowdownAction.SHOW
MUCK = ShowdownAction.MUCK
INTERACTIVE = ShowdownKind.INTERACTIVE

HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
MUCKER_BEST_HOLES = {1: "Jd Jh", 2: "Ah Ad", 3: "3s 4s"}
BOARD = "2c 7d 9h Jc Ks"

SET_OF_KINGS = HandRank(HandCategory.THREE_OF_A_KIND, (13, 11, 9))
PAIR_OF_ACES = HandRank(HandCategory.ONE_PAIR, (14, 13, 11, 9))
KING_HIGH = HandRank(HandCategory.HIGH_CARD, (13, 11, 9, 7, 4))
SET_OF_JACKS = HandRank(HandCategory.THREE_OF_A_KIND, (11, 13, 9))

type NewHand = Callable[..., PokerHand]


def bet(target: int) -> Action:
    return Action(ActionType.BET, target)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def play(hand: PokerHand, *actions: tuple[int, Action]) -> None:
    for seat, action in actions:
        apply_action(hand, seat, action)


def next_street(hand: PokerHand) -> None:
    deal_next_street(hand)
    start_betting_round(hand)


def check_street(hand: PokerHand) -> None:
    assert hand.betting is not None
    while hand.betting.current_actor is not None:
        apply_action(hand, hand.betting.current_actor, CHECK)


def seat_state(hand: PokerHand, seat: int) -> Any:
    return next(state for state in hand.players if state.seat_number == seat)


def snapshot(hand: PokerHand) -> dict[str, Any]:
    """Everything about the hand, for comparing before and after (the deck by its size: drawing is its only change)."""
    return {
        "street": hand.street,
        "board": list(hand.board),
        "burned": list(hand.burned_cards),
        "deck": len(hand.deck),
        "betting": copy.deepcopy(hand.betting),
        "settlement": hand.settlement,
        "showdown": hand.showdown,
        "history": hand.history,
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


def decide(hand: PokerHand, *decisions: tuple[int, ShowdownAction]) -> None:
    for seat, action in decisions:
        apply_showdown_action(hand, seat, action)


def showdown_of(hand: PokerHand) -> Showdown:
    assert hand.showdown is not None
    return hand.showdown


def derived(hand: PokerHand) -> tuple[object, ...]:
    """The showdown's derived state: shown, mucked, contenders, current decider, complete."""
    showdown = showdown_of(hand)
    return (showdown.shown, showdown.mucked, showdown.contenders, showdown.current_decider, showdown.is_complete)


def settled(hand: PokerHand) -> Settlement:
    assert hand.settlement is not None
    return hand.settlement


def settle_and_check(hand: PokerHand) -> Settlement:
    """Settle the hand and check what every successful interactive settlement keeps; return the settlement.

    Chips are conserved, every pot's shares add up to its amount, each award's pot is the pot as derived, only
    contenders are paid, the settlement ranks exactly the shown seats in hand order, and the showdown is the same
    object, unchanged, as before. The history gains exactly `HandSettled` of the settlement (the showdown has already
    recorded its start and decisions) and is then complete.
    """
    starting_chips = {state.seat_number: state.player.stack + state.total_contribution for state in hand.players}
    showdown = showdown_of(hand)
    showdown_before = (showdown.kind, showdown.order, showdown.decisions)
    pots_before = pots(hand)
    middle_before = middle_pot(hand)
    before = snapshot(hand)

    settle_hand(hand)

    settlement = settled(hand)
    assert hand.showdown is showdown
    assert hand.history.events == (*before["history"].events, HandSettled(settlement))
    assert hand.history.is_complete and hand.history.settlement == settlement
    assert (showdown.kind, showdown.order, showdown.decisions) == showdown_before
    assert [award.pot for award in settlement.pot_awards] == list(pots_before) == list(pots(hand))
    assert middle_pot(hand) == middle_before == sum(settlement.payouts.values())
    assert all(sum(chips for _, chips in award.shares) == award.pot.amount for award in settlement.pot_awards)
    assert set(settlement.payouts) <= set(showdown.contenders)
    assert not set(settlement.payouts) & set(showdown.mucked)
    assert [seat for seat, _ in settlement.showdown_ranks] == [
        state.seat_number for state in hand.players if state.seat_number in showdown.shown
    ]
    for state in hand.players:
        assert state.player.stack == starting_chips[state.seat_number] - state.total_contribution + (
            settlement.payouts.get(state.seat_number, 0)
        )
        assert state.folded is next(s for s in before["players"] if s[0] == state.seat_number)[2]
    assert sum(state.player.stack for state in hand.players) == sum(starting_chips.values())
    return settlement


def assert_settle_rejected(hand: PokerHand, error: type[Exception]) -> None:
    """`settle_hand` raises `error` and leaves the hand exactly as it was, showdown included (the same object)."""
    before = snapshot(hand)

    with pytest.raises(error):
        settle_hand(hand)

    assert snapshot(hand) == before
    assert hand.settlement is None
    assert hand.showdown is before["showdown"]


@pytest.fixture
def new_hand(stacked_hand: NewHand) -> NewHand:
    """A stacked hand checked down to the river (whose round is started); the river round is then completed by
    `river_actions`, or checked down when there are none. The showdown is started unless `start` is False."""

    def build(
        river_actions: tuple[tuple[int, Action], ...] = (),
        holes: dict[int, str] | None = None,
        board: str = BOARD,
        button: int = 1,
        start: bool = True,
    ) -> PokerHand:
        hand = stacked_hand(holes or HOLES, board, button=button)
        initialize_betting(hand, STAKES)
        deal_hole_cards(hand)
        assert hand.betting is not None
        while hand.betting.current_actor is not None:
            actor = hand.betting.current_actor
            apply_action(hand, actor, CHECK if hand.betting.pending_actors == {actor} else CALL)
        while hand.street is not Street.TURN:
            next_street(hand)
            check_street(hand)
        next_street(hand)
        if river_actions:
            play(hand, *river_actions)
        else:
            check_street(hand)
        if start:
            start_showdown(hand)
        return hand

    return build


# =============================================================================
# SHOWDOWN SEQUENCES THAT SETTLE
# =============================================================================


def test_a_river_bet_sets_the_order_and_only_the_best_of_the_remaining_contenders_is_paid(new_hand: NewHand) -> None:
    """Seat 3 bets and is called, so the order is 3, 1, 2. Seat 3 shows, seat 1 mucks the best hand and seat 2 shows:
    the pot goes to the better of seats 3 and 2. Seat 1 is neither ranked nor paid."""
    hand = new_hand(river_actions=((2, CHECK), (3, bet(10)), (1, CALL), (2, CALL)), holes=MUCKER_BEST_HOLES)
    assert showdown_of(hand) == Showdown(INTERACTIVE, (3, 1, 2))

    apply_showdown_action(hand, 3, SHOW)
    assert derived(hand) == ((3,), (), (3, 1, 2), 1, False)
    apply_showdown_action(hand, 1, MUCK)
    assert derived(hand) == ((3,), (1,), (3, 2), 2, False)
    apply_showdown_action(hand, 2, SHOW)
    assert derived(hand) == ((3, 2), (1,), (3, 2), None, True)

    settlement = settle_and_check(hand)

    assert settlement.payouts == {2: 60}
    assert settlement.showdown_ranks == ((2, PAIR_OF_ACES), (3, KING_HIGH))
    assert [seat_state(hand, seat).player.stack for seat in (1, 2, 3)] == [980, 1040, 980]


def test_everyone_showing_completes_the_showdown_and_ranks_every_seat(new_hand: NewHand) -> None:
    hand = new_hand(river_actions=((2, bet(20)), (3, CALL), (1, CALL)))
    decide(hand, (2, SHOW), (3, SHOW))
    assert not showdown_of(hand).is_complete
    decide(hand, (1, SHOW))
    assert showdown_of(hand).is_complete
    assert len(showdown_of(hand).decisions) == len(showdown_of(hand).order)

    settlement = settle_and_check(hand)

    assert settlement.payouts == {2: 90}
    assert settlement.showdown_ranks == ((1, PAIR_OF_ACES), (2, SET_OF_KINGS), (3, KING_HIGH))


def test_a_mucked_seat_is_not_paid_even_though_it_holds_the_best_hand(new_hand: NewHand) -> None:
    """Seat 2 holds the best hand and mucks; the best of the shown hands (seat 1's pair of aces) takes the pot."""
    hand = new_hand()
    decide(hand, (2, MUCK), (3, SHOW), (1, SHOW))

    settlement = settle_and_check(hand)

    assert settlement.payouts == {1: 30}
    assert settlement.showdown_ranks == ((1, PAIR_OF_ACES), (3, KING_HIGH))
    assert seat_state(hand, 2).player.stack == 990


# =============================================================================
# THE LAST CONTENDER WINS UNSHOWN
# =============================================================================


def test_all_but_one_muck_and_the_last_contender_wins_every_pot_without_a_rank(new_hand: NewHand) -> None:
    """Seats 2 and 3 muck. Seat 1 is never asked to decide, is not ranked, and takes the pot."""
    hand = new_hand(holes=MUCKER_BEST_HOLES)
    decide(hand, (2, MUCK), (3, MUCK))
    assert showdown_of(hand).decisions == (MUCK, MUCK)

    settlement = settle_and_check(hand)

    assert settlement.payouts == {1: 30}
    assert settlement.showdown_ranks == ()
    assert showdown_of(hand).shown == ()
    assert showdown_of(hand).decisions == (MUCK, MUCK)


def test_the_last_contender_wins_even_when_every_mucked_seat_held_a_better_hand(new_hand: NewHand) -> None:
    """Seat 2's set of kings mucks, seat 3 mucks; seat 1 with only a pair of aces is paid and nobody else is."""
    hand = new_hand()
    decide(hand, (2, MUCK), (3, MUCK))

    settlement = settle_and_check(hand)

    assert settlement.payouts == {1: 30}
    assert settlement.showdown_ranks == ()
    assert [seat_state(hand, seat).player.stack for seat in (1, 2, 3)] == [1020, 990, 990]


def test_heads_up_a_first_muck_gives_the_other_seat_the_pot_unshown(new_hand: NewHand) -> None:
    hand = new_hand(holes={1: "Ah Ad", 2: "Kd Kh"})
    decide(hand, (2, MUCK))

    settlement = settle_and_check(hand)

    assert settlement.payouts == {1: 20}
    assert settlement.showdown_ranks == ()


def test_an_unshown_winner_needs_neither_a_valid_hand_nor_any_evaluation(
    new_hand: NewHand, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing is ranked or validated when nobody showed: the last contender's hole cards are never touched."""
    hand = new_hand()
    decide(hand, (2, MUCK), (3, MUCK))
    seat_state(hand, 1).hole_cards.pop()
    seat_state(hand, 2).hole_cards.clear()

    def fail(cards: list[Card]) -> HandRank:
        raise AssertionError("nothing may be evaluated")

    monkeypatch.setattr(showdown_module, "evaluate_best", fail)

    assert settle_and_check(hand).payouts == {1: 30}


# =============================================================================
# TIES AND ODD CHIPS AMONG THE SHOWN
# =============================================================================


def test_a_tie_among_the_shown_hands_splits_the_pot_while_a_better_mucked_hand_takes_nothing(new_hand: NewHand) -> None:
    """Seat 2's two pair would win, but it mucks. Seats 3 and 1 show tied pairs of kings with ace-queen kickers and
    split the 30-chip pot."""
    hand = new_hand(holes={1: "As Qh", 2: "9c 9d", 3: "Ac Qd"}, board="Kc Kd 7h 4s 2d")
    decide(hand, (2, MUCK), (3, SHOW), (1, SHOW))

    settlement = settle_and_check(hand)

    assert [award.shares for award in settlement.pot_awards] == [((3, 15), (1, 15))]
    assert settlement.payouts == {3: 15, 1: 15}
    assert settlement.showdown_ranks[0][1] == settlement.showdown_ranks[1][1]


def test_odd_chips_among_the_shown_contenders_follow_the_odd_chip_order(stacked_hand: NewHand) -> None:
    """Seat 1 raises to 25, seats 2 and 3 call: a 75-chip pot. Seat 2 mucks the best hand; seats 3 and 1 tie, so seat 3,
    the first of them left of the button, takes the odd chip."""
    hand = stacked_hand({1: "As Qh", 2: "9c 9d", 3: "Ac Qd"}, "Kc Kd 7h 4s 2d")
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    play(hand, (1, raise_to(25)), (2, CALL), (3, CALL))
    while hand.street is not Street.TURN:
        next_street(hand)
        check_street(hand)
    next_street(hand)
    check_street(hand)
    start_showdown(hand)
    decide(hand, (2, MUCK), (3, SHOW), (1, SHOW))

    settlement = settle_and_check(hand)

    assert [award.shares for award in settlement.pot_awards] == [((3, 38), (1, 37))]
    assert [seat_state(hand, seat).player.stack for seat in (1, 2, 3)] == [1012, 975, 1013]


# =============================================================================
# FOLDED DEAD MONEY AND THE POT AS ORIGINALLY CONTESTED
# =============================================================================


@pytest.fixture
def dead_money_hand(new_hand: NewHand, stacked_hand: NewHand) -> PokerHand:
    """Seat 2 folds on the flop after putting 30 in, leaving seats 3 and 1 with 70 each: dead money at one level and a
    second level above it make two pots with the same eligible seats. The river is checked down; the showdown has
    started and the decision order is seat 3, then seat 1. Seat 1 holds a pair of aces, seat 3 only king high."""
    hand = stacked_hand(HOLES, BOARD)
    initialize_betting(hand, STAKES)
    deal_hole_cards(hand)
    play(hand, (1, CALL), (2, CALL), (3, CHECK))
    next_street(hand)
    play(hand, (2, bet(20)), (3, CALL), (1, raise_to(60)), (2, FOLD), (3, CALL))
    while hand.street is not Street.TURN:
        next_street(hand)
        check_street(hand)
    next_street(hand)
    check_street(hand)
    start_showdown(hand)
    return hand


def test_folded_dead_money_funds_the_pots_but_the_folded_seat_is_never_eligible(dead_money_hand: PokerHand) -> None:
    hand = dead_money_hand
    folded = seat_state(hand, 2)

    assert folded.folded
    assert folded.total_contribution == 30
    assert pots(hand) == (Pot(90, frozenset({1, 3})), Pot(80, frozenset({1, 3})))
    assert all(2 not in pot.eligible_seats for pot in pots(hand))
    assert sum(pot.amount for pot in pots(hand)) == middle_pot(hand) == 170
    assert showdown_of(hand) == Showdown(INTERACTIVE, (3, 1))


def test_a_player_who_reaches_showdown_and_mucks_stays_in_the_pots_as_originally_contested(
    dead_money_hand: PokerHand,
) -> None:
    """Seat 1 reaches the showdown live, so it is eligible for both pots, and then mucks. The muck changes nothing about
    the pots as derived: seat 1 is still in their eligible seats, before the settlement and in each award's pot."""
    hand = dead_money_hand
    pots_before = pots(hand)
    assert all(1 in pot.eligible_seats for pot in pots_before)

    decide(hand, (3, SHOW), (1, MUCK))

    assert pots(hand) == pots_before
    assert all(1 in pot.eligible_seats for pot in pots(hand))
    assert seat_state(hand, 1).folded is False
    assert showdown_of(hand).mucked == (1,)

    settlement = settle_and_check(hand)

    assert [award.pot for award in settlement.pot_awards] == list(pots_before)
    assert all(1 in award.pot.eligible_seats for award in settlement.pot_awards)
    assert pots(hand) == pots_before


def test_the_mucked_player_is_excluded_only_by_the_final_contenders_and_the_contender_takes_both_pots(
    dead_money_hand: PokerHand,
) -> None:
    """Seat 1's pair of aces beats seat 3's king high, but seat 1 mucked: it gets no share of either pot, seat 3 takes
    both whole, and the folded seat 2's dead money goes to seat 3 as well."""
    hand = dead_money_hand
    decide(hand, (3, SHOW), (1, MUCK))

    settlement = settle_and_check(hand)

    assert [award.shares for award in settlement.pot_awards] == [((3, 90),), ((3, 80),)]
    assert settlement.payouts == {3: 170}
    assert settlement.showdown_ranks == ((3, KING_HIGH),)
    assert [seat_state(hand, seat).player.stack for seat in (1, 2, 3)] == [930, 970, 1100]


def test_when_the_first_decider_mucks_the_remaining_seat_wins_every_pot_unshown(dead_money_hand: PokerHand) -> None:
    hand = dead_money_hand
    decide(hand, (3, MUCK))
    assert showdown_of(hand).is_complete

    settlement = settle_and_check(hand)

    assert [award.shares for award in settlement.pot_awards] == [((1, 90),), ((1, 80),)]
    assert settlement.showdown_ranks == ()


def test_the_better_shown_hand_wins_both_dead_money_pots_when_both_show(dead_money_hand: PokerHand) -> None:
    hand = dead_money_hand
    decide(hand, (3, SHOW), (1, SHOW))

    settlement = settle_and_check(hand)

    assert [award.shares for award in settlement.pot_awards] == [((1, 90),), ((1, 80),)]
    assert settlement.showdown_ranks == ((1, PAIR_OF_ACES), (3, KING_HIGH))


# =============================================================================
# SETTLING AT THE WRONG TIME
# =============================================================================


def test_a_river_showdown_that_was_never_started_cannot_be_settled(new_hand: NewHand) -> None:
    hand = new_hand(start=False)

    assert_settle_rejected(hand, ShowdownNotStartedError)
    assert hand.showdown is None


def test_a_started_showdown_with_no_decisions_cannot_be_settled(new_hand: NewHand) -> None:
    hand = new_hand()

    assert_settle_rejected(hand, ShowdownIncompleteError)


@pytest.mark.parametrize(
    "decisions",
    [[(2, SHOW)], [(2, MUCK)], [(2, SHOW), (3, SHOW)], [(2, SHOW), (3, MUCK)], [(2, MUCK), (3, SHOW)]],
    ids=["show", "muck", "show-show", "show-muck", "muck-show"],
)
def test_a_showdown_with_decisions_still_pending_cannot_be_settled(
    new_hand: NewHand, decisions: list[tuple[int, ShowdownAction]]
) -> None:
    hand = new_hand()
    decide(hand, *decisions)
    assert not showdown_of(hand).is_complete

    assert_settle_rejected(hand, ShowdownIncompleteError)


def test_finishing_the_decisions_lets_a_rejected_hand_settle(new_hand: NewHand) -> None:
    hand = new_hand()
    assert_settle_rejected(hand, ShowdownIncompleteError)
    decide(hand, (2, SHOW))
    assert_settle_rejected(hand, ShowdownIncompleteError)
    decide(hand, (3, SHOW), (1, SHOW))

    assert settle_and_check(hand).payouts == {2: 30}


def test_a_river_round_still_in_progress_is_not_ready_rather_than_not_started(new_hand: NewHand) -> None:
    """Readiness is judged before the showdown: an unanswered river bet has no showdown to start yet."""
    hand = new_hand(river_actions=((2, bet(10)), (3, CALL)), start=False)

    assert_settle_rejected(hand, ShowdownNotReadyError)


# =============================================================================
# NOTHING LEAKS FROM HANDS THAT DID NOT SHOW
# =============================================================================


@pytest.mark.parametrize(
    ("decisions", "shown"),
    [
        ([(2, SHOW), (3, SHOW), (1, SHOW)], {1, 2, 3}),
        ([(2, SHOW), (3, MUCK), (1, SHOW)], {1, 2}),
        ([(2, MUCK), (3, SHOW), (1, MUCK)], {3}),
        ([(2, MUCK), (3, MUCK)], set()),
        ([(2, SHOW), (3, MUCK), (1, MUCK)], {2}),
    ],
    ids=["all-show", "one-mucks", "show-between-mucks", "unshown-winner", "last-mucks-after-show"],
)
def test_the_settlement_ranks_exactly_the_shown_seats_and_only_their_cards_are_evaluated(
    new_hand: NewHand,
    monkeypatch: pytest.MonkeyPatch,
    decisions: list[tuple[int, ShowdownAction]],
    shown: set[int],
) -> None:
    hand = new_hand()
    decide(hand, *decisions)
    evaluated: list[list[Card]] = []
    real_evaluate_best = showdown_module.evaluate_best

    def spy(seven_cards: list[Card]) -> HandRank:
        evaluated.append(list(seven_cards))
        return real_evaluate_best(seven_cards)

    monkeypatch.setattr(showdown_module, "evaluate_best", spy)

    settlement = settle_and_check(hand)

    assert {seat for seat, _ in settlement.showdown_ranks} == shown == set(showdown_of(hand).shown)
    assert evaluated == [[*state.hole_cards, *hand.board] for state in hand.players if state.seat_number in shown]
    for seat in {1, 2, 3} - shown:
        assert not any(card in cards for cards in evaluated for card in seat_state(hand, seat).hole_cards)


def test_a_mucked_seat_is_not_validated_even_without_valid_hole_cards(new_hand: NewHand) -> None:
    """Only shown hands are ranked, so a mucked seat's hole cards are not even checked."""
    hand = new_hand()
    decide(hand, (2, SHOW), (3, MUCK), (1, SHOW))
    seat_state(hand, 3).hole_cards.pop()

    assert {seat for seat, _ in settle_and_check(hand).showdown_ranks} == {1, 2}


def test_a_shown_seat_without_exactly_two_hole_cards_is_rejected_unchanged(new_hand: NewHand) -> None:
    hand = new_hand()
    decide(hand, (2, SHOW), (3, SHOW), (1, SHOW))
    seat_state(hand, 3).hole_cards.pop()

    assert_settle_rejected(hand, InvalidHoleCardCountError)
