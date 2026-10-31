"""`BettingState.last_aggressor`: the seat of the current round's last bet or raise, reached through real actions.

The hands are four-handed, seats 5 (button), 8 (small blind), 1 (big blind) and 3 (first to act preflop); on every later
street seat 8 acts first. Stacks are deep unless a test says otherwise.
"""

from collections.abc import Callable

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.rounds import start_betting_round
from go_poker.game.betting.state import BettingState
from go_poker.game.poker_hand import PokerHand
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street

type HandFactory = Callable[..., PokerHand]
type BettingLookup = Callable[[PokerHand], BettingState]
type Play = Callable[..., None]

FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
BUTTON = 5
DEEP = {5: 1000, 8: 1000, 1: 1000, 3: 1000}


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def bet(target: int) -> Action:
    return Action(ActionType.BET, target)


def flop_round(started_hand: HandFactory, play: Play, stacks: dict[int, int] = DEEP) -> PokerHand:
    """Everyone calls preflop, the big blind checks, then the flop is dealt and its round started."""
    hand = started_hand(stacks, button_seat_number=BUTTON)
    deal_hole_cards(hand)
    play(hand, (3, CALL), (5, CALL), (8, CALL), (1, CHECK))
    deal_next_street(hand)
    start_betting_round(hand)
    return hand


def test_nobody_is_the_aggressor_after_the_blinds_are_posted(started_hand: HandFactory, betting: BettingLookup) -> None:
    """The blinds are posted, not bet."""
    assert betting(started_hand(DEEP, button_seat_number=BUTTON)).last_aggressor is None


def test_a_preflop_raise_makes_the_raiser_the_aggressor(
    started_hand: HandFactory, betting: BettingLookup, play: Play
) -> None:
    hand = started_hand(DEEP, button_seat_number=BUTTON)

    play(hand, (3, raise_to(30)))

    assert betting(hand).last_aggressor == 3


def test_the_last_raiser_is_the_aggressor_not_the_first(
    started_hand: HandFactory, betting: BettingLookup, play: Play
) -> None:
    hand = started_hand(DEEP, button_seat_number=BUTTON)

    play(hand, (3, raise_to(30)), (5, raise_to(90)))
    assert betting(hand).last_aggressor == 5

    play(hand, (8, raise_to(300)))
    assert betting(hand).last_aggressor == 8


def test_calls_and_folds_leave_the_aggressor_unchanged(
    started_hand: HandFactory, betting: BettingLookup, play: Play
) -> None:
    hand = started_hand(DEEP, button_seat_number=BUTTON)

    play(hand, (3, raise_to(30)), (5, CALL), (8, FOLD))

    assert betting(hand).last_aggressor == 3


def test_a_postflop_bet_makes_the_bettor_the_aggressor_and_checks_leave_it_unset(
    started_hand: HandFactory, betting: BettingLookup, play: Play
) -> None:
    hand = flop_round(started_hand, play)
    assert betting(hand).last_aggressor is None

    play(hand, (8, CHECK))
    assert betting(hand).last_aggressor is None

    play(hand, (1, bet(20)))
    assert betting(hand).last_aggressor == 1

    play(hand, (3, CALL))
    assert betting(hand).last_aggressor == 1


def test_a_short_all_in_raise_makes_the_player_the_aggressor(
    started_hand: HandFactory, betting: BettingLookup, play: Play
) -> None:
    """Seat 3 has 15 chips, so raising all-in to 15 is below the full minimum raise target of 20."""
    hand = started_hand({5: 1000, 8: 1000, 1: 1000, 3: 15}, button_seat_number=BUTTON)

    play(hand, (3, raise_to(15)))

    assert betting(hand).current_bet == 15
    assert betting(hand).last_full_raise_size == 10  # a short all-in is not a full raise
    assert betting(hand).last_aggressor == 3


def test_a_short_all_in_bet_makes_the_player_the_aggressor(
    started_hand: HandFactory, betting: BettingLookup, play: Play
) -> None:
    """Seat 8 has 5 chips left on the flop, below the minimum bet of 10, so betting them all is a short all-in bet."""
    hand = flop_round(started_hand, play, {5: 1000, 8: 15, 1: 1000, 3: 1000})
    assert betting(hand).current_actor == 8

    play(hand, (8, bet(5)))

    assert betting(hand).current_bet == 5
    assert betting(hand).last_full_raise_size == 10
    assert betting(hand).last_aggressor == 8


def test_a_new_betting_round_clears_the_aggressor(
    started_hand: HandFactory, betting: BettingLookup, play: Play
) -> None:
    hand = started_hand(DEEP, button_seat_number=BUTTON)
    deal_hole_cards(hand)
    play(hand, (3, raise_to(30)), (5, CALL), (8, CALL), (1, CALL))
    assert betting(hand).last_aggressor == 3

    deal_next_street(hand)
    start_betting_round(hand)

    assert betting(hand).last_aggressor is None
