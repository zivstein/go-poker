from collections.abc import Callable

import pytest

from go_poker.game.betting.initialization import (
    BettingAlreadyInitializedError,
    BettingNotPreflopError,
    initialize_betting,
)
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingState
from go_poker.game.game_lifecycle import start_game
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind, Position
from go_poker.game.street import Street
from go_poker.game.table import Table
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street

type HandFactory = Callable[..., PokerHand]
type SeatLookup = Callable[[PokerHand], dict[int, HandPlayerState]]
type BettingLookup = Callable[[PokerHand], BettingState]
type PlayerSnapshotter = Callable[[PokerHand], dict[int, tuple[int, int, int, bool, bool]]]


# =============================================================================
# BLIND POSTING AND FIRST ACTOR
# =============================================================================


def test_multiway_blinds_are_posted_and_first_player_after_big_blind_acts(
    make_hand: HandFactory,
    by_seat: SeatLookup,
    betting: BettingLookup,
    player_snapshot: PlayerSnapshotter,
    stakes: Stakes,
) -> None:
    """Four-handed, the blinds post real chips, everyone is pending and the player after the big blind acts first.
    Posting a blind is not an action, so nobody has acted yet."""
    hand = make_hand({1: 1000, 3: 1000, 5: 1000, 8: 1000}, button_seat_number=5)
    seats = by_seat(hand)
    assert [hand_player.seat_number for hand_player in hand.players] == [5, 8, 1, 3]
    assert (seats[8].blind, seats[1].blind, seats[3].position) == (Blind.SMALL, Blind.BIG, Position.UTG)

    initialize_betting(hand, stakes)

    assert player_snapshot(hand) == {
        5: (1000, 0, 0, False, False),  # button
        8: (995, 5, 5, False, False),  # small blind
        1: (990, 10, 10, False, False),  # big blind
        3: (1000, 0, 0, False, False),  # UTG
    }
    assert all(hp.player.stack + hp.total_contribution == 1000 for hp in hand.players)
    assert betting(hand) == BettingState(
        street=Street.PREFLOP,
        stakes=stakes,
        current_bet=10,
        last_full_raise_size=10,
        current_actor=3,
        pending_actors={1, 3, 5, 8},
        acted_at_bet={},
    )


def test_three_handed_first_actor_wraps_to_the_button(
    make_hand: HandFactory, betting: BettingLookup, stakes: Stakes
) -> None:
    """Three-handed, the player clockwise after the big blind is the button."""
    hand = make_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    initialize_betting(hand, stakes)
    assert betting(hand).current_actor == 1
    assert betting(hand).pending_actors == {1, 2, 3}


def test_heads_up_button_posts_small_blind_and_acts_first(
    make_hand: HandFactory, betting: BettingLookup, player_snapshot: PlayerSnapshotter, stakes: Stakes
) -> None:
    """Heads-up, the button posts the small blind and acts first; both players are pending."""
    hand = make_hand({3: 1000, 7: 1000}, button_seat_number=7)
    initialize_betting(hand, stakes)
    assert player_snapshot(hand) == {
        7: (995, 5, 5, False, False),  # button and small blind
        3: (990, 10, 10, False, False),  # big blind
    }
    assert betting(hand).current_actor == 7
    assert betting(hand).pending_actors == {3, 7}


# =============================================================================
# REJECTED INITIALIZATION
# =============================================================================


def test_repeated_initialization_is_rejected_without_changes(
    make_hand: HandFactory, betting: BettingLookup, player_snapshot: PlayerSnapshotter, stakes: Stakes
) -> None:
    """A hand's betting is initialized once; a second attempt changes no stack, contribution or betting state."""
    hand = make_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    initialize_betting(hand, stakes)
    betting_state = betting(hand)
    before = player_snapshot(hand)

    with pytest.raises(BettingAlreadyInitializedError):
        initialize_betting(hand, stakes)

    assert player_snapshot(hand) == before
    assert hand.betting is betting_state
    assert betting_state.current_actor == 1
    assert betting_state.pending_actors == {1, 2, 3}


def test_hand_past_preflop_is_rejected_without_changes(
    make_hand: HandFactory, player_snapshot: PlayerSnapshotter, stakes: Stakes
) -> None:
    """Betting is initialized on the preflop street; a hand dealt to the flop is rejected before any chips move."""
    hand = make_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    deal_hole_cards(hand)
    deal_next_street(hand)
    before = player_snapshot(hand)
    board_before = list(hand.board)

    with pytest.raises(BettingNotPreflopError):
        initialize_betting(hand, stakes)

    assert player_snapshot(hand) == before
    assert hand.street is Street.FLOP
    assert hand.board == board_before
    assert hand.betting is None


# =============================================================================
# BLINDS THAT USE A PLAYER'S LAST CHIPS
# =============================================================================


def test_blind_posted_with_last_chips_marks_player_all_in_and_not_pending(
    make_hand: HandFactory, by_seat: SeatLookup, betting: BettingLookup, stakes: Stakes
) -> None:
    """A big blind posted with exactly the whole stack puts that player all-in, so they owe no action."""
    hand = make_hand({1: 10, 3: 1000, 5: 1000, 8: 1000}, button_seat_number=5)
    initialize_betting(hand, stakes)
    big_blind = by_seat(hand)[1]
    assert (big_blind.player.stack, big_blind.total_contribution, big_blind.all_in) == (0, 10, True)
    assert betting(hand).current_actor == 3
    assert betting(hand).pending_actors == {3, 5, 8}


@pytest.mark.parametrize(
    "short_seat_number, pending",
    [
        pytest.param(8, {5, 1, 3}, id="small-blind"),
        pytest.param(1, {5, 8, 3}, id="big-blind"),
    ],
)
def test_short_blind_posts_the_whole_stack_and_keeps_the_full_big_blind_bet(
    short_seat_number: int,
    pending: set[int],
    make_hand: HandFactory,
    by_seat: SeatLookup,
    betting: BettingLookup,
    stakes: Stakes,
) -> None:
    """A blind player with 3 chips, fewer than their blind, posts all 3 and is all-in, so they owe no action. The
    current bet and the last full raise size still start at the full big blind of 10."""
    hand = make_hand({5: 1000, 8: 1000, 1: 1000, 3: 1000, short_seat_number: 3}, button_seat_number=5)
    initialize_betting(hand, stakes)

    short_blind = by_seat(hand)[short_seat_number]
    assert (short_blind.player.stack, short_blind.street_contribution, short_blind.total_contribution) == (0, 3, 3)
    assert short_blind.all_in is True
    assert betting(hand) == BettingState(
        street=Street.PREFLOP,
        stakes=stakes,
        current_bet=10,
        last_full_raise_size=10,
        current_actor=3,
        pending_actors=pending,
        acted_at_bet={},
    )


def test_heads_up_big_blind_all_in_below_the_small_blind_leaves_the_round_complete(
    make_hand: HandFactory, player_snapshot: PlayerSnapshotter, betting: BettingLookup, stakes: Stakes
) -> None:
    """Heads-up, the big blind is all-in for 3, less than the small blind's 5. The small blind already has more in
    front than the big blind can contest, so it owes nothing: nobody is pending and the round is complete as soon as
    betting is initialized. Its extra 2 stay in front (unmatched chips are not returned yet)."""
    hand = make_hand({3: 3, 7: 1000}, button_seat_number=7)
    initialize_betting(hand, stakes)

    assert player_snapshot(hand) == {
        7: (995, 5, 5, False, False),  # button and small blind
        3: (0, 3, 3, False, True),  # big blind
    }
    assert betting(hand).current_bet == 10
    assert betting(hand).current_actor is None
    assert betting(hand).pending_actors == set()


def test_heads_up_small_blind_all_in_leaves_the_round_complete(
    make_hand: HandFactory, by_seat: SeatLookup, betting: BettingLookup, stakes: Stakes
) -> None:
    """When the small blind is all-in by posting and the big blind owes nothing, nobody can respond: no one acts."""
    hand = make_hand({3: 1000, 7: 5}, button_seat_number=7)
    initialize_betting(hand, stakes)
    assert by_seat(hand)[7].all_in is True
    assert betting(hand).current_actor is None
    assert betting(hand).pending_actors == set()


def test_heads_up_big_blind_all_in_leaves_only_the_small_blind_to_act(
    make_hand: HandFactory, by_seat: SeatLookup, betting: BettingLookup, stakes: Stakes
) -> None:
    """When the big blind is all-in by posting, the small blind still owes chips and is the only pending actor."""
    hand = make_hand({3: 10, 7: 1000}, button_seat_number=7)
    initialize_betting(hand, stakes)
    assert by_seat(hand)[3].all_in is True
    assert betting(hand).current_actor == 7
    assert betting(hand).pending_actors == {7}


# =============================================================================
# HAND-START SEQUENCE
# =============================================================================


def test_started_hand_initializes_betting_then_deals_hole_cards(
    betting: BettingLookup, player_snapshot: PlayerSnapshotter, stakes: Stakes
) -> None:
    """Start the game, initialize betting, then deal Texas Hold'em hole cards to the same hand."""
    table = Table(9)
    for seat_number in (1, 3, 5, 8):
        table.sit_in(Player(f"P{seat_number}", stack=1000), seat_number)
    hand = start_game(table, lambda seats: 5)

    initialize_betting(hand, stakes)
    deal_hole_cards(hand)

    assert {seat: snapshot[:3] for seat, snapshot in player_snapshot(hand).items()} == {
        5: (1000, 0, 0),
        8: (995, 5, 5),
        1: (990, 10, 10),
        3: (1000, 0, 0),
    }
    assert all(len(hand_player.hole_cards) == 2 for hand_player in hand.players)
    assert betting(hand).street is Street.PREFLOP
    assert betting(hand).current_actor == 3
