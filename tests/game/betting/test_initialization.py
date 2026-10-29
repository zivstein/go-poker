import pytest

from go_poker.core.deck import Deck
from go_poker.game.betting.initialization import (
    BettingAlreadyInitializedError,
    BettingNotPreflopError,
    ShortBlindAllInNotSupportedError,
    initialize_betting,
)
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingState
from go_poker.game.game_lifecycle import start_game
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.position import Blind, Position
from go_poker.game.position_assignment import assign_hand_seats
from go_poker.game.street import Street
from go_poker.game.table import Table
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards, deal_next_street

STAKES = Stakes(small_blind=5, big_blind=10)

type PlayerSnapshot = tuple[int, int, int, bool, bool]


def make_hand(stacks: dict[int, int], button_seat_number: int) -> PokerHand:
    """Build a hand clockwise from the button, with each seat's player holding the given stack."""
    assignments = assign_hand_seats(tuple(stacks), button_seat_number)
    players = tuple(
        HandPlayerState(
            player=Player(f"P{seat_number}", stack=stacks[seat_number], status=PlayerStatus.READY),
            seat_number=seat_number,
            position=assignment.position,
            blind=assignment.blind,
        )
        for seat_number, assignment in assignments.items()
    )
    return PokerHand(players=players, deck=Deck())


def by_seat(hand: PokerHand) -> dict[int, HandPlayerState]:
    return {hand_player.seat_number: hand_player for hand_player in hand.players}


def player_snapshot(hand: PokerHand) -> dict[int, PlayerSnapshot]:
    return {
        hand_player.seat_number: (
            hand_player.player.stack,
            hand_player.street_contribution,
            hand_player.total_contribution,
            hand_player.folded,
            hand_player.all_in,
        )
        for hand_player in hand.players
    }


def betting(hand: PokerHand) -> BettingState:
    assert hand.betting is not None
    return hand.betting


# =============================================================================
# BLIND POSTING AND FIRST ACTOR
# =============================================================================


def test_multiway_blinds_are_posted_and_first_player_after_big_blind_acts() -> None:
    """Four-handed, the blinds post real chips, everyone is pending and the player after the big blind acts first."""
    hand = make_hand({1: 1000, 3: 1000, 5: 1000, 8: 1000}, button_seat_number=5)
    seats = by_seat(hand)
    assert [hand_player.seat_number for hand_player in hand.players] == [5, 8, 1, 3]
    assert (seats[8].blind, seats[1].blind, seats[3].position) == (Blind.SMALL, Blind.BIG, Position.UTG)

    initialize_betting(hand, STAKES)

    assert player_snapshot(hand) == {
        5: (1000, 0, 0, False, False),  # button
        8: (995, 5, 5, False, False),  # small blind
        1: (990, 10, 10, False, False),  # big blind
        3: (1000, 0, 0, False, False),  # UTG
    }
    assert all(hp.player.stack + hp.total_contribution == 1000 for hp in hand.players)
    assert betting(hand) == BettingState(
        street=Street.PREFLOP,
        stakes=STAKES,
        current_bet=10,
        last_full_raise_size=10,
        current_actor=3,
        pending_actors={1, 3, 5, 8},
    )


def test_three_handed_first_actor_wraps_to_the_button() -> None:
    """Three-handed, the player clockwise after the big blind is the button."""
    hand = make_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    initialize_betting(hand, STAKES)
    assert betting(hand).current_actor == 1
    assert betting(hand).pending_actors == {1, 2, 3}


def test_heads_up_button_posts_small_blind_and_acts_first() -> None:
    """Heads-up, the button posts the small blind and acts first; both players are pending."""
    hand = make_hand({3: 1000, 7: 1000}, button_seat_number=7)
    initialize_betting(hand, STAKES)
    assert player_snapshot(hand) == {
        7: (995, 5, 5, False, False),  # button and small blind
        3: (990, 10, 10, False, False),  # big blind
    }
    assert betting(hand).current_actor == 7
    assert betting(hand).pending_actors == {3, 7}


# =============================================================================
# REJECTED INITIALIZATION
# =============================================================================


def test_repeated_initialization_is_rejected_without_changes() -> None:
    """A hand's betting is initialized once; a second attempt changes no stack, contribution or betting state."""
    hand = make_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    initialize_betting(hand, STAKES)
    betting_state = betting(hand)
    before = player_snapshot(hand)

    with pytest.raises(BettingAlreadyInitializedError):
        initialize_betting(hand, STAKES)

    assert player_snapshot(hand) == before
    assert hand.betting is betting_state
    assert betting_state.current_actor == 1
    assert betting_state.pending_actors == {1, 2, 3}


def test_hand_past_preflop_is_rejected_without_changes() -> None:
    """Betting is initialized on the preflop street; a hand dealt to the flop is rejected before any chips move."""
    hand = make_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    deal_hole_cards(hand)
    deal_next_street(hand)
    before = player_snapshot(hand)
    board_before = list(hand.board)

    with pytest.raises(BettingNotPreflopError):
        initialize_betting(hand, STAKES)

    assert player_snapshot(hand) == before
    assert hand.street is Street.FLOP
    assert hand.board == board_before
    assert hand.betting is None


@pytest.mark.parametrize(
    "stacks",
    [
        pytest.param({5: 1000, 8: 4, 1: 1000, 3: 1000}, id="small-blind-short"),
        pytest.param({5: 1000, 8: 1000, 1: 9, 3: 1000}, id="big-blind-short"),
    ],
)
def test_short_blind_all_in_is_not_supported_yet_and_changes_nothing(stacks: dict[int, int]) -> None:
    """A blind player with chips but fewer than their blind would post a short all-in, which Milestone 2 does not
    support yet (deferred to Milestone 3); initialization is rejected before any chips move."""
    hand = make_hand(stacks, button_seat_number=5)
    before = player_snapshot(hand)

    with pytest.raises(ShortBlindAllInNotSupportedError):
        initialize_betting(hand, STAKES)

    assert player_snapshot(hand) == before
    assert hand.betting is None


# =============================================================================
# BLINDS THAT USE A PLAYER'S LAST CHIPS
# =============================================================================


def test_blind_posted_with_last_chips_marks_player_all_in_and_not_pending() -> None:
    """A big blind posted with exactly the whole stack puts that player all-in, so they owe no action."""
    hand = make_hand({1: 10, 3: 1000, 5: 1000, 8: 1000}, button_seat_number=5)
    initialize_betting(hand, STAKES)
    big_blind = by_seat(hand)[1]
    assert (big_blind.player.stack, big_blind.total_contribution, big_blind.all_in) == (0, 10, True)
    assert betting(hand).current_actor == 3
    assert betting(hand).pending_actors == {3, 5, 8}


def test_heads_up_small_blind_all_in_leaves_the_round_complete() -> None:
    """When the small blind is all-in by posting and the big blind owes nothing, nobody can respond: no one acts."""
    hand = make_hand({3: 1000, 7: 5}, button_seat_number=7)
    initialize_betting(hand, STAKES)
    assert by_seat(hand)[7].all_in is True
    assert betting(hand).current_actor is None
    assert betting(hand).pending_actors == set()


def test_heads_up_big_blind_all_in_leaves_only_the_small_blind_to_act() -> None:
    """When the big blind is all-in by posting, the small blind still owes chips and is the only pending actor."""
    hand = make_hand({3: 10, 7: 1000}, button_seat_number=7)
    initialize_betting(hand, STAKES)
    assert by_seat(hand)[3].all_in is True
    assert betting(hand).current_actor == 7
    assert betting(hand).pending_actors == {7}


# =============================================================================
# HAND-START SEQUENCE
# =============================================================================


def test_started_hand_initializes_betting_then_deals_hole_cards() -> None:
    """Start the game, initialize betting, then deal Texas Hold'em hole cards to the same hand."""
    table = Table(9)
    for seat_number in (1, 3, 5, 8):
        table.sit_in(Player(f"P{seat_number}", stack=1000), seat_number)
    hand = start_game(table, lambda seats: 5)

    initialize_betting(hand, STAKES)
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
