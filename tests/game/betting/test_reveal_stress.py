"""Seeded river showdowns with nobody all-in: the reveal against an oracle that tracks the river aggressor on its own.

`test_hand_stress` reaches a non-all-in river showdown in only a handful of its seeds, because its generator is
aggressive and its stacks often small. Here the stacks are deep and the play is passive and rarely folds, so a bet or
raise never reaches an all-in and most hands reach the river contested. The expected reveal is computed from the
actions applied on the river alone, never from `BettingState.last_aggressor`, so the engine's aggressor is checked too.
The seeds are fixed, so a failure names the seed that reproduces it.
"""

import copy
import random
from collections.abc import Callable

import pytest

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import initialize_betting
from go_poker.game.betting.legal_actions import legal_actions
from go_poker.game.betting.rounds import is_round_complete, start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingState
from go_poker.game.poker_hand import PokerHand
from go_poker.game.reveal import Reveal, RevealKind
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street
from go_poker.game.variants.texas_holdem.showdown import (
    HandAlreadyRevealedError,
    reveal_hands,
    settle_hand,
)

type HandFactory = Callable[..., PokerHand]

SEEDS = range(300)
DEEP_STACK = 1_000_000  # no generated bet or raise comes near it
MIN_SHOWDOWNS = 150  # how many seeds must end in a contested river showdown
MIN_PER_SHAPE = 20  # and how many of those must reach each shape of show order listed in `Shapes`

FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)


def choose_action(rng: random.Random, hand: PokerHand) -> Action:
    legal = legal_actions(hand)
    if legal.can_check:
        if legal.can_bet and rng.random() < 0.35:
            assert legal.min_full_target is not None
            return Action(ActionType.BET, legal.min_full_target + rng.randint(0, 40))
        return CHECK
    roll = rng.random()
    if roll < 0.08:
        return FOLD
    if roll < 0.2 and legal.min_full_target is not None:
        return Action(ActionType.RAISE, legal.min_full_target + rng.randint(0, 40))
    return CALL


def play_round(rng: random.Random, hand: PokerHand) -> int | None:
    """Play the current round to its end; return the seat of the last bet or raise applied in it, by this driver's own
    count."""
    assert hand.betting is not None
    aggressor = None
    while not is_round_complete(hand.betting):
        actor = hand.betting.current_actor
        assert actor is not None
        action = choose_action(rng, hand)
        apply_action(hand, actor, action)
        if action.type in (ActionType.BET, ActionType.RAISE):
            aggressor = actor
    return aggressor


def expected_show_order(hand: PokerHand, aggressor: int | None) -> tuple[int, ...]:
    """Live seats clockwise from the seat after the button, rotated to start at the aggressor."""
    seats = [state.seat_number for state in hand.players]  # the button first
    live = [seat for seat in (*seats[1:], seats[0]) if not folded(hand, seat)]
    start = live.index(aggressor) if aggressor is not None else 0
    return tuple(live[start:] + live[:start])


def play_to_river_showdown(seed: int, make_hand: HandFactory) -> tuple[PokerHand, int | None] | None:
    """Play the seed's hand to a completed river round and return it with the river's aggressor, or None when the hand
    was won uncontested before the river."""
    rng = random.Random(seed)
    seat_numbers = sorted(rng.sample(range(1, 10), rng.randint(2, 9)))
    hand = make_hand({seat: DEEP_STACK for seat in seat_numbers}, button_seat_number=rng.choice(seat_numbers))
    hand.deck.shuffle(_rng=random.Random(f"deck-{seed}"))
    initialize_betting(hand, Stakes(small_blind=50, big_blind=100))
    deal_hole_cards(hand)
    aggressor = play_round(rng, hand)
    while hand.street is not Street.RIVER:
        if sum(not state.folded for state in hand.players) < 2:
            return None
        deal_next_street(hand)
        start_betting_round(hand)
        aggressor = play_round(rng, hand)
    if sum(not state.folded for state in hand.players) < 2:
        return None
    return hand, aggressor


def folded(hand: PokerHand, seat: int) -> bool:
    return next(state for state in hand.players if state.seat_number == seat).folded


def betting(hand: PokerHand) -> BettingState:
    assert hand.betting is not None
    return hand.betting


class Shapes:
    """Shapes of show order the seeds must keep reaching."""

    def __init__(self) -> None:
        self.no_bet = 0  # nobody bet on the river
        self.aggressor_first = 0  # the aggressor is the first live seat left of the button, so the order is canonical
        self.aggressor_after = 0  # the aggressor shows first and the order wraps back to the seats before it
        self.button_aggressor = 0  # the button is the aggressor, so it shows first
        self.folded_skipped = 0  # a seat that folded sits between live seats of the order


def test_river_showdown_reveal_matches_the_independent_show_order(make_hand: HandFactory) -> None:
    for seed in SEEDS:
        result = play_to_river_showdown(seed, make_hand)
        if result is not None:
            try:
                check_showdown(*result)
            except AssertionError as error:
                raise AssertionError(f"seed {seed}") from error


def check_showdown(hand: PokerHand, aggressor: int | None) -> None:
    assert not any(state.all_in for state in hand.players if not state.folded)
    assert betting(hand).last_aggressor == aggressor
    expected = Reveal(RevealKind.SHOWDOWN, expected_show_order(hand, aggressor))

    direct = copy.deepcopy(hand)
    settle_hand(direct)
    assert direct.reveal == expected

    reveal_hands(hand)
    assert hand.reveal == expected
    reveal = hand.reveal
    with pytest.raises(HandAlreadyRevealedError):
        reveal_hands(hand)
    settle_hand(hand)
    assert hand.reveal is reveal


def test_the_seeds_keep_reaching_every_shape_of_river_show_order(make_hand: HandFactory) -> None:
    """The seed set is useful only while it keeps reaching the shapes of show order it checks."""
    shapes = Shapes()
    showdowns = 0
    for seed in SEEDS:
        result = play_to_river_showdown(seed, make_hand)
        if result is None:
            continue
        hand, aggressor = result
        showdowns += 1
        seats = [state.seat_number for state in hand.players]
        canonical = [*seats[1:], seats[0]]
        live = [seat for seat in canonical if not folded(hand, seat)]
        shapes.no_bet += aggressor is None
        shapes.aggressor_first += aggressor is not None and aggressor == live[0]
        shapes.aggressor_after += aggressor is not None and aggressor != live[0]
        shapes.button_aggressor += aggressor == seats[0]
        shapes.folded_skipped += any(
            folded(hand, seat) and canonical.index(live[0]) < canonical.index(seat) < canonical.index(live[-1])
            for seat in canonical
        )

    assert showdowns >= MIN_SHOWDOWNS, showdowns
    counts = vars(shapes)
    assert all(count >= MIN_PER_SHAPE for count in counts.values()), counts
