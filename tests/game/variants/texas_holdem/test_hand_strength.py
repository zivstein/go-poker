"""Hold'em derived hand strength: `holdem_hand_strength(hole_cards, board)` and `hand_strength(hand, seat)`.

The pure function is tested with literal cards: the rank, the exact best five in order of significance, the
description, the equal-rank edge cases and every input error. `hand_strength` is tested through the real dealing,
betting and showdown operations from a deck stacked by the shared `stacked_hand` fixture, with a seeded random test of
the invariants over many deals.
"""

import copy
import random
from collections.abc import Callable, Sequence
from itertools import combinations
from typing import Any

import pytest

from go_poker.core.best_hand import BestHand
from go_poker.core.card import Card, Rank, Suit
from go_poker.core.evaluator import DuplicateCardsError, WrongCardAmountError, evaluate_best, evaluate_five
from go_poker.core.hand_rank import HandCategory, HandRank
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.legal_actions import legal_actions
from go_poker.game.betting.pots import middle_pot, pots
from go_poker.game.betting.stakes import Stakes
from go_poker.game.poker_hand import PokerHand
from go_poker.game.showdown import ShowdownAction
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import InvalidHoleCardCountError, deal_hole_cards
from go_poker.game.variants.texas_holdem.hand_flow import act, begin_hand, current_actor
from go_poker.game.variants.texas_holdem.hand_strength import SeatNotInHandError, hand_strength, holdem_hand_strength

type Cards = Callable[[str], list[Card]]

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)

# --- the pure function ---------------------------------------------------------------------------------------------


def strength(cards: Cards, hole: str, board: str) -> BestHand:
    result = holdem_hand_strength(cards(hole), cards(board))
    assert result is not None
    return result


def test_preflop_has_no_strength(cards: Cards) -> None:
    assert holdem_hand_strength(cards("As Kd"), []) is None


@pytest.mark.parametrize(
    "hole, board",
    [
        pytest.param("As 3d", "Kc 9h 7d", id="flop-5-cards"),
        pytest.param("As 3d", "Kc 9h 7d 5s", id="turn-6-cards"),
        pytest.param("As 3d", "Kc 9h 7d 5s 2c", id="river-7-cards"),
    ],
)
def test_every_street_evaluates_the_best_five(cards: Cards, hole: str, board: str) -> None:
    best = strength(cards, hole, board)
    assert best.rank == evaluate_best([*cards(hole), *cards(board)])
    assert best.rank.category is HandCategory.HIGH_CARD
    assert best.description == "Ace high"
    assert len(set(best.cards)) == 5
    assert set(best.cards) <= {*cards(hole), *cards(board)}


def test_a_flop_hand_is_all_five_cards_in_significance_order(cards: Cards) -> None:
    best = strength(cards, "3s 9d", "Kc 9h 3d")
    assert best.rank == HandRank(HandCategory.TWO_PAIR, (9, 3, 13))
    assert list(best.cards) == cards("9h 9d 3d 3s Kc")


@pytest.mark.parametrize(
    "hole, board, category, expected_cards, description",
    [
        pytest.param("As 3d", "Kc 9h 7d 5s 2c", HandCategory.HIGH_CARD, "As Kc 9h 7d 5s", "Ace high", id="high-card"),
        pytest.param("8s 8d", "Ac 9h 4d 3s 2c", HandCategory.ONE_PAIR, "8s 8d Ac 9h 4d", "Pair of Eights", id="pair"),
        pytest.param(
            "6s 6d", "Ac 9h 4d 3s Kc", HandCategory.ONE_PAIR, "6s 6d Ac Kc 9h", "Pair of Sixes", id="pair-sixes"
        ),
        pytest.param(
            "Ks 4d",
            "Kc 4h 9d 2s 7c",
            HandCategory.TWO_PAIR,
            "Kc Ks 4h 4d 9d",
            "Two pair, Kings and Fours",
            id="two-pair",
        ),
        pytest.param(
            "7s 7d",
            "7c Ah 2d 9s 4c",
            HandCategory.THREE_OF_A_KIND,
            "7c 7s 7d Ah 9s",
            "Three of a kind, Sevens",
            id="trips",
        ),
        pytest.param(
            "9s 8d",
            "7c 6h 5d Kc 2s",
            HandCategory.STRAIGHT,
            "9s 8d 7c 6h 5d",
            "Nine-high straight",
            id="straight",
        ),
        pytest.param(
            "As 2d",
            "3c 4h 5d Kc Qs",
            HandCategory.STRAIGHT,
            "5d 4h 3c 2d As",
            "Five-high straight",
            id="wheel",
        ),
        pytest.param("As 3s", "Ks 9s 2s 7d 7h", HandCategory.FLUSH, "As Ks 9s 3s 2s", "Ace-high flush", id="flush"),
        pytest.param(
            "8s Ad",
            "8d 8h Ac 3s 2c",
            HandCategory.FULL_HOUSE,
            "8d 8h 8s Ac Ad",
            "Eights full of Aces",
            id="full-house",
        ),
        pytest.param(
            "Qs Qd",
            "Qc Qh 2d 9s 3c",
            HandCategory.FOUR_OF_A_KIND,
            "Qc Qh Qs Qd 9s",
            "Four of a kind, Queens",
            id="quads",
        ),
        pytest.param(
            "9h 8h",
            "7h 6h 5h Kc 2s",
            HandCategory.STRAIGHT_FLUSH,
            "9h 8h 7h 6h 5h",
            "Nine-high straight flush",
            id="straight-flush",
        ),
        pytest.param(
            "Ah 2h",
            "3h 4h 5h Kc 9s",
            HandCategory.STRAIGHT_FLUSH,
            "5h 4h 3h 2h Ah",
            "Five-high straight flush",
            id="wheel-straight-flush",
        ),
        pytest.param(
            "Ah Kh",
            "Qh Jh Th 2c 3d",
            HandCategory.STRAIGHT_FLUSH,
            "Ah Kh Qh Jh Th",
            "Royal flush",
            id="royal-flush",
        ),
    ],
)
def test_category_cards_order_and_description(
    cards: Cards, hole: str, board: str, category: HandCategory, expected_cards: str, description: str
) -> None:
    best = strength(cards, hole, board)
    assert best.rank.category is category
    assert list(best.cards) == cards(expected_cards)
    assert best.description == description


def test_the_wheel_is_listed_ace_low_not_ace_high(cards: Cards) -> None:
    best = strength(cards, "Ac 2d", "3h 4s 5c 9d Jh")
    assert best.rank == HandRank(HandCategory.STRAIGHT, (5,))
    assert [card.rank for card in best.cards] == [5, 4, 3, 2, 14]


def test_a_broadway_straight_keeps_the_ace_high(cards: Cards) -> None:
    best = strength(cards, "Ac Kd", "Qh Js Tc 9d 2h")
    assert list(best.cards) == cards("Ac Kd Qh Js Tc")
    assert best.description == "Ace-high straight"


def test_two_pair_with_three_pairs_uses_the_best_kicker(cards: Cards) -> None:
    """Three pairs: the best two pair, and the kicker is the highest remaining card, even from the third pair."""
    best = strength(cards, "Ks 4d", "Kc 4h 9d 9s 7c")
    assert best.rank == HandRank(HandCategory.TWO_PAIR, (13, 9, 7))
    assert list(best.cards) == cards("Kc Ks 9d 9s 7c")


# --- equal-rank best-five selection --------------------------------------------------------------------------------


def test_a_board_straight_plays_when_a_hole_card_has_the_same_rank(cards: Cards) -> None:
    best = strength(cards, "9d 2s", "5c 6d 7h 8s 9c")
    assert list(best.cards) == cards("9c 8s 7h 6d 5c")


def test_a_board_straight_plays_when_a_hole_card_is_lower(cards: Cards) -> None:
    best = strength(cards, "2d 3s", "5c 6d 7h 8s 9c")
    assert list(best.cards) == cards("9c 8s 7h 6d 5c")


def test_a_board_flush_plays_when_a_hole_card_adds_nothing(cards: Cards) -> None:
    best = strength(cards, "2s 3d", "Ac Kc 9c 5c 4c")
    assert best.rank.category is HandCategory.FLUSH
    assert list(best.cards) == cards("Ac Kc 9c 5c 4c")


def test_a_board_two_pair_plays_against_a_hole_card_equal_to_its_kicker(cards: Cards) -> None:
    """The hole 4d pairs the board's 4s, so kings and nines can take either 4 as the kicker."""
    best = strength(cards, "4d 2c", "Ks Kd 9c 9h 4s")
    assert best.rank == HandRank(HandCategory.TWO_PAIR, (13, 9, 4))
    assert list(best.cards) == cards("Ks Kd 9c 9h 4s")


def test_a_hole_card_strictly_better_than_the_board_kicker_is_used(cards: Cards) -> None:
    best = strength(cards, "Ad 2c", "Ks Kd 9c 9h 4s")
    assert best.rank == HandRank(HandCategory.TWO_PAIR, (13, 9, 14))
    assert list(best.cards) == cards("Ks Kd 9c 9h Ad")


def test_a_hole_card_strictly_better_than_the_board_card_is_used(cards: Cards) -> None:
    best = strength(cards, "Td 2s", "5c 6d 7h 8s 9c")
    assert best.rank == HandRank(HandCategory.STRAIGHT, (10,))
    assert list(best.cards) == cards("Td 9c 8s 7h 6d")


def test_a_lower_board_card_equal_in_rank_to_a_hole_card_prefers_fewer_hole_cards(cards: Cards) -> None:
    """The 9-high straight can use the board 9s with only the hole 5s, or the hole 9d too: the board 9s is chosen."""
    best = strength(cards, "5s 9d", "6c 7d 8h 9s 2s")
    assert list(best.cards) == cards("9s 8h 7d 6c 5s")


def test_two_equal_hole_cards_are_resolved_by_deal_order(cards: Cards) -> None:
    assert list(strength(cards, "9s 9d", "6c 7d 8h Tc 2s").cards) == cards("Tc 9s 8h 7d 6c")


def test_two_equal_hole_cards_are_resolved_by_deal_order_reversed(cards: Cards) -> None:
    assert list(strength(cards, "9d 9s", "6c 7d 8h Tc 2s").cards) == cards("Tc 9d 8h 7d 6c")


def test_equal_board_kickers_are_resolved_by_deal_order(cards: Cards) -> None:
    """Quad sevens with a king kicker: the king dealt on the flop is chosen, not the one on the river."""
    best = strength(cards, "7s 7d", "Kc 7c 7h 2s Kd")
    assert best.rank == HandRank(HandCategory.FOUR_OF_A_KIND, (7, 13))
    assert list(best.cards) == cards("7c 7h 7s 7d Kc")


def test_equal_board_kickers_are_resolved_by_deal_order_reversed(cards: Cards) -> None:
    best = strength(cards, "7s 7d", "Kd 7c 7h 2s Kc")
    assert list(best.cards) == cards("7c 7h 7s 7d Kd")


def test_equal_board_cards_are_resolved_by_deal_order_on_the_turn(cards: Cards) -> None:
    """On the turn the later of two equal kickers is the turn card, so the flop king still wins."""
    best = strength(cards, "7s 7d", "Kc 7c 7h Kd")
    assert list(best.cards) == cards("7c 7h 7s 7d Kc")


def test_equal_rank_cards_are_listed_in_deal_order_board_first(cards: Cards) -> None:
    best = strength(cards, "Js Jd", "Jc 3h 3d 9s 2c")
    assert best.rank == HandRank(HandCategory.FULL_HOUSE, (11, 3))
    assert list(best.cards) == cards("Jc Js Jd 3h 3d")


def test_a_pair_split_between_hole_card_and_board_lists_the_board_card_first(cards: Cards) -> None:
    best = strength(cards, "Ad 2c", "9s Ah 7d 5c 3s")
    assert list(best.cards) == cards("Ah Ad 9s 7d 5c")


def test_flush_cards_in_the_same_suit_are_listed_high_to_low(cards: Cards) -> None:
    best = strength(cards, "9h 2h", "Ah Kh 5h 6c 7d")
    assert list(best.cards) == cards("Ah Kh 9h 5h 2h")


# --- inputs --------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("hole", ["", "As", "As Kd Qh"])
@pytest.mark.parametrize("board", ["", "2c 7d 9h"])
def test_exactly_two_hole_cards_are_required(cards: Cards, hole: str, board: str) -> None:
    with pytest.raises(InvalidHoleCardCountError):
        holdem_hand_strength(cards(hole), cards(board))


@pytest.mark.parametrize("board", ["2c", "2c 7d", "2c 7d 9h Jc Ks 3s", "2c 7d 9h Jc Ks 3s 4s 5s"])
def test_the_board_must_have_zero_three_four_or_five_cards(cards: Cards, board: str) -> None:
    with pytest.raises(WrongCardAmountError, match="board"):
        holdem_hand_strength(cards("As Ad"), cards(board))


@pytest.mark.parametrize(
    "hole, board",
    [
        pytest.param("As As", "", id="duplicate-hole-preflop"),
        pytest.param("As Ad", "As 7d 9h", id="hole-and-board"),
        pytest.param("As Ad", "2c 2c 9h", id="board-only"),
        pytest.param("As Ad", "Ad 7d 9h Jc Ks", id="river"),
    ],
)
def test_duplicate_cards_are_rejected_even_preflop(cards: Cards, hole: str, board: str) -> None:
    with pytest.raises(DuplicateCardsError):
        holdem_hand_strength(cards(hole), cards(board))


def test_the_hole_card_count_is_checked_before_the_board_size(cards: Cards) -> None:
    with pytest.raises(InvalidHoleCardCountError):
        holdem_hand_strength(cards("As"), cards("2c 7d"))


def test_the_board_size_is_checked_before_duplicates(cards: Cards) -> None:
    with pytest.raises(WrongCardAmountError):
        holdem_hand_strength(cards("As As"), cards("2c 2c"))


def test_the_hole_card_count_is_checked_before_duplicates(cards: Cards) -> None:
    with pytest.raises(InvalidHoleCardCountError):
        holdem_hand_strength(cards("As As Ad"), [])


def test_inputs_are_accepted_as_any_sequence_and_never_changed(cards: Cards) -> None:
    hole, board = cards("9s 9d"), cards("6c 7d 8h Tc 2s")
    hole_before, board_before = list(hole), list(board)
    from_lists = holdem_hand_strength(hole, board)
    assert hole == hole_before and board == board_before
    assert holdem_hand_strength(tuple(hole), tuple(board)) == from_lists


def test_the_result_holds_fresh_tuples_not_the_inputs(cards: Cards) -> None:
    board = cards("5c 6d 7h 8s 9c")
    best = holdem_hand_strength(cards("2d 3s"), board)
    assert best is not None
    cards_before = best.cards
    board.reverse()
    board.clear()
    assert isinstance(best.cards, tuple) and best.cards == cards_before == tuple(cards("9c 8s 7h 6d 5c"))


# --- through a real hand -------------------------------------------------------------------------------------------

HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
BOARD = "2c 7d 9h Jc Ks"
HAND_ORDER = (1, 2, 3)


def new_hand(stacked_hand: Callable[..., PokerHand]) -> PokerHand:
    return stacked_hand(HOLES, BOARD)


def advance_to(hand: PokerHand, street: Street) -> None:
    """Let everyone call or check until the hand reaches the street."""
    while hand.street is not street:
        seat = current_actor(hand)
        assert seat is not None
        act(hand, seat, CHECK if legal_actions(hand).can_check else CALL)


def check_down_to(hand: PokerHand, street: Street) -> None:
    """Begin the hand, then let everyone call or check until it reaches the street."""
    begin_hand(hand, STAKES)
    advance_to(hand, street)


def check_to_showdown(hand: PokerHand) -> None:
    """Check the river round, which starts the interactive showdown."""
    while hand.showdown is None:
        seat = current_actor(hand)
        assert seat is not None
        act(hand, seat, CHECK)


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


def read(hand: PokerHand, cards: Cards, seat: int) -> tuple[str, list[Card], HandCategory]:
    best = hand_strength(hand, seat)
    assert best is not None
    return best.description, list(best.cards), best.rank.category


def test_the_hand_strength_follows_the_street(stacked_hand: Callable[..., PokerHand], cards: Cards) -> None:
    hand = new_hand(stacked_hand)
    deal_hole_cards(hand)
    assert [hand_strength(hand, seat) for seat in HAND_ORDER] == [None, None, None]

    hand = new_hand(stacked_hand)
    begin_hand(hand, STAKES)
    assert hand.street is Street.PREFLOP
    assert [hand_strength(hand, seat) for seat in HAND_ORDER] == [None, None, None]

    advance_to(hand, Street.FLOP)
    assert read(hand, cards, 1) == ("Pair of Aces", cards("Ah Ad 9h 7d 2c"), HandCategory.ONE_PAIR)
    assert read(hand, cards, 2) == ("Pair of Kings", cards("Kd Kh 9h 7d 2c"), HandCategory.ONE_PAIR)
    assert read(hand, cards, 3) == ("Nine high", cards("9h 7d 4s 3s 2c"), HandCategory.HIGH_CARD)

    advance_to(hand, Street.TURN)
    assert read(hand, cards, 1) == ("Pair of Aces", cards("Ah Ad Jc 9h 7d"), HandCategory.ONE_PAIR)
    assert read(hand, cards, 3) == ("Jack high", cards("Jc 9h 7d 4s 3s"), HandCategory.HIGH_CARD)

    advance_to(hand, Street.RIVER)
    assert read(hand, cards, 1) == ("Pair of Aces", cards("Ah Ad Ks Jc 9h"), HandCategory.ONE_PAIR)
    assert read(hand, cards, 2) == ("Three of a kind, Kings", cards("Ks Kd Kh Jc 9h"), HandCategory.THREE_OF_A_KIND)
    assert read(hand, cards, 3) == ("King high", cards("Ks Jc 9h 7d 4s"), HandCategory.HIGH_CARD)


def test_an_undealt_hand_has_no_hole_cards_to_evaluate(stacked_hand: Callable[..., PokerHand]) -> None:
    hand = new_hand(stacked_hand)
    with pytest.raises(InvalidHoleCardCountError):
        hand_strength(hand, 1)


def test_an_unknown_seat_is_rejected(stacked_hand: Callable[..., PokerHand]) -> None:
    hand = new_hand(stacked_hand)
    check_down_to(hand, Street.FLOP)
    before = snapshot(hand)
    for seat in (0, 4, -1, 99):
        with pytest.raises(SeatNotInHandError):
            hand_strength(hand, seat)
    assert snapshot(hand) == before
    assert issubclass(SeatNotInHandError, ValueError)


def test_an_unknown_seat_is_rejected_before_the_hole_cards_are_checked(stacked_hand: Callable[..., PokerHand]) -> None:
    hand = new_hand(stacked_hand)
    with pytest.raises(SeatNotInHandError):
        hand_strength(hand, 9)


def test_a_folded_seat_keeps_its_strength(stacked_hand: Callable[..., PokerHand], cards: Cards) -> None:
    hand = new_hand(stacked_hand)
    check_down_to(hand, Street.FLOP)
    before = hand_strength(hand, 2)
    actor = current_actor(hand)
    assert actor == 2
    act(hand, 2, FOLD)
    assert next(state for state in hand.players if state.seat_number == 2).folded
    assert hand_strength(hand, 2) == before
    advance_to(hand, Street.RIVER)
    assert read(hand, cards, 2) == ("Three of a kind, Kings", cards("Ks Kd Kh Jc 9h"), HandCategory.THREE_OF_A_KIND)


def test_every_seat_of_an_uncontested_hand_keeps_its_strength(
    stacked_hand: Callable[..., PokerHand], cards: Cards
) -> None:
    hand = new_hand(stacked_hand)
    check_down_to(hand, Street.FLOP)
    act(hand, 2, FOLD)
    act(hand, 3, FOLD)
    assert hand.settlement is not None
    assert read(hand, cards, 1) == ("Pair of Aces", cards("Ah Ad 9h 7d 2c"), HandCategory.ONE_PAIR)
    assert read(hand, cards, 2) == ("Pair of Kings", cards("Kd Kh 9h 7d 2c"), HandCategory.ONE_PAIR)
    assert read(hand, cards, 3) == ("Nine high", cards("9h 7d 4s 3s 2c"), HandCategory.HIGH_CARD)


def test_a_mucked_seat_keeps_its_strength_and_a_settled_hand_is_readable(
    stacked_hand: Callable[..., PokerHand], cards: Cards
) -> None:
    hand = new_hand(stacked_hand)
    check_down_to(hand, Street.RIVER)
    check_to_showdown(hand)
    mucked_before = hand_strength(hand, 3)
    decisions = {2: ShowdownAction.SHOW, 3: ShowdownAction.MUCK, 1: ShowdownAction.SHOW}
    for seat, decision in decisions.items():
        assert current_actor(hand) == seat
        act(hand, seat, decision)

    assert hand.settlement is not None
    assert hand.showdown is not None and hand.showdown.mucked == (3,)
    assert hand_strength(hand, 3) == mucked_before
    assert read(hand, cards, 3) == ("King high", cards("Ks Jc 9h 7d 4s"), HandCategory.HIGH_CARD)

    for seat, rank in hand.settlement.showdown_ranks:
        best = hand_strength(hand, seat)
        assert best is not None and best.rank == rank
    assert [seat for seat, _ in hand.settlement.showdown_ranks] == [1, 2]


def test_the_river_strength_matches_the_settlement_rank_of_every_shown_seat(
    stacked_hand: Callable[..., PokerHand],
) -> None:
    hand = new_hand(stacked_hand)
    check_down_to(hand, Street.RIVER)
    check_to_showdown(hand)
    while hand.settlement is None:
        seat = current_actor(hand)
        assert seat is not None
        act(hand, seat, ShowdownAction.SHOW)
    assert hand.settlement.showdown_ranks
    for seat, rank in hand.settlement.showdown_ranks:
        best = hand_strength(hand, seat)
        assert best is not None and best.rank == rank


def test_reading_the_strength_never_changes_the_hand(stacked_hand: Callable[..., PokerHand]) -> None:
    hand = new_hand(stacked_hand)
    for street in (Street.PREFLOP, Street.FLOP, Street.TURN, Street.RIVER):
        if street is Street.PREFLOP:
            begin_hand(hand, STAKES)
        else:
            advance_to(hand, street)
        before = snapshot(hand)
        results = [hand_strength(hand, seat) for seat in HAND_ORDER]
        assert snapshot(hand) == before
        assert [hand_strength(hand, seat) for seat in HAND_ORDER] == results

    check_to_showdown(hand)
    before = snapshot(hand)
    for seat in HAND_ORDER:
        hand_strength(hand, seat)
    assert snapshot(hand) == before
    while hand.settlement is None:
        seat = current_actor(hand)
        assert seat is not None
        act(hand, seat, ShowdownAction.SHOW)
        after_decision = snapshot(hand)
        for read_seat in HAND_ORDER:
            hand_strength(hand, read_seat)
        assert snapshot(hand) == after_decision


def test_the_result_does_not_alias_the_hands_cards(stacked_hand: Callable[..., PokerHand]) -> None:
    hand = new_hand(stacked_hand)
    check_down_to(hand, Street.FLOP)
    best = hand_strength(hand, 1)
    assert best is not None
    frozen = best.cards
    hand.board.clear()
    hand.players[0].hole_cards.clear()
    assert best.cards == frozen


# --- seeded invariants ---------------------------------------------------------------------------------------------

DEALS_PER_BOARD_SIZE = 3000
_NAMES = {
    14: "Ace",
    13: "King",
    12: "Queen",
    11: "Jack",
    10: "Ten",
    9: "Nine",
    8: "Eight",
    7: "Seven",
    6: "Six",
    5: "Five",
    4: "Four",
    3: "Three",
    2: "Two",
}
_KEYWORDS = {
    HandCategory.HIGH_CARD: " high",
    HandCategory.ONE_PAIR: "Pair of ",
    HandCategory.TWO_PAIR: "Two pair, ",
    HandCategory.THREE_OF_A_KIND: "Three of a kind, ",
    HandCategory.STRAIGHT: "-high straight",
    HandCategory.FLUSH: "-high flush",
    HandCategory.FULL_HOUSE: " full of ",
    HandCategory.FOUR_OF_A_KIND: "Four of a kind, ",
    HandCategory.STRAIGHT_FLUSH: "straight flush",
}


def significance(card: Card, five: Sequence[Card], rank: HandRank) -> tuple[int, int]:
    """Sort key of a card within the five: more copies of its rank first, then the higher rank (the wheel's ace low)."""
    copies = sum(other.rank == card.rank for other in five)
    wheel = rank.category in (HandCategory.STRAIGHT, HandCategory.STRAIGHT_FLUSH) and rank.tiebreakers == (5,)
    value = 1 if wheel and card.rank == Rank.ACE else int(card.rank)
    return -copies, -value


def random_deal(rng: random.Random, board_size: int) -> tuple[list[Card], list[Card]]:
    """Two hole cards and a board, from a full deck or from a small one that makes ties, quads and flushes common."""
    if rng.random() < 0.5:
        deck = [Card(rank, suit) for rank in Rank for suit in Suit]
    else:
        deck = [Card(rank, suit) for rank in rng.sample(list(Rank), 6) for suit in rng.sample(list(Suit), 2)]
    dealt = rng.sample(deck, 2 + board_size)
    return dealt[:2], dealt[2:]


def check_invariants(hole: list[Card], board: list[Card]) -> None:
    best = holdem_hand_strength(hole, board)
    assert best is not None
    all_cards = [*hole, *board]
    assert best.rank == evaluate_best(all_cards)
    assert len(set(best.cards)) == 5 and set(best.cards) <= set(all_cards)
    assert evaluate_five(best.cards) == best.rank

    # Independent brute force: the fewest hole cards among the best-ranked fives, then the earliest deal positions.
    position = {card: index for index, card in enumerate([*board, *hole])}
    best_fives = [combo for combo in combinations(all_cards, 5) if evaluate_five(combo) == best.rank]
    expected = min(
        best_fives,
        key=lambda combo: (sum(card in hole for card in combo), sorted(position[card] for card in combo)),
    )
    assert set(best.cards) == set(expected)
    assert sum(card in hole for card in best.cards) == min(sum(card in hole for card in c) for c in best_fives)

    keys = [(*significance(card, best.cards, best.rank), position[card]) for card in best.cards]
    assert keys == sorted(keys), "non-increasing significance, equal ranks in deal order"

    assert _KEYWORDS[best.rank.category] in best.description
    primary = _NAMES[best.rank.tiebreakers[0]]
    if best.rank.category is HandCategory.STRAIGHT_FLUSH and best.rank.tiebreakers[0] == Rank.ACE:
        assert best.description == "Royal flush"
    else:
        assert primary in best.description


@pytest.mark.parametrize("board_size", [3, 4, 5])
def test_random_deals_keep_the_invariants(board_size: int) -> None:
    rng = random.Random(f"hand-strength-{board_size}")
    for _ in range(DEALS_PER_BOARD_SIZE):
        hole, board = random_deal(rng, board_size)
        check_invariants(hole, board)
