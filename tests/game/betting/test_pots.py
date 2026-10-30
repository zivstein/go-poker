from collections.abc import Callable, Collection

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.pots import Pot, middle_pot, pots
from go_poker.game.poker_hand import PokerHand
from go_poker.game.variants.texas_holdem.dealing import deal_hole_cards

# Pot layering is checked on hand-built collected contributions; the integration scenarios reach such states through
# real betting actions.

type HandFactory = Callable[..., PokerHand]
type HandSnapshotter = Callable[[PokerHand], object]
type Play = Callable[..., None]

CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)


def pot(amount: int, *eligible_seats: int) -> Pot:
    return Pot(amount, frozenset(eligible_seats))


def collected_hand(
    make_hand: HandFactory,
    contributions: dict[int, int],
    *,
    folded: Collection[int] = (),
    all_in: Collection[int] = (),
) -> PokerHand:
    """A hand after a collected betting round: each seat has the given chips committed and nothing in front."""
    hand = make_hand({seat_number: 1000 for seat_number in contributions}, button_seat_number=min(contributions))
    for hand_player in hand.players:
        hand_player.total_contribution = contributions[hand_player.seat_number]
        hand_player.player.stack = 0 if hand_player.seat_number in all_in else 1000 - hand_player.total_contribution
        hand_player.folded = hand_player.seat_number in folded
        hand_player.all_in = hand_player.seat_number in all_in
    return hand


# =============================================================================
# MIDDLE POT
# =============================================================================


def test_middle_pot_holds_only_collected_chips(
    started_hand: HandFactory, hand_snapshot: HandSnapshotter, play: Play
) -> None:
    """Three-handed preflop, the posted blinds are chips in front and nothing has been collected: the middle pot is
    empty and there are no pots. Once the round completes it is collected, and the middle pot holds every player's
    total contribution. The middle pot and the pots are derived on request and change nothing."""
    hand = started_hand({1: 1000, 2: 1000, 3: 1000}, button_seat_number=1)
    before = hand_snapshot(hand)

    assert (middle_pot(hand), pots(hand)) == (0, ())
    assert hand_snapshot(hand) == before

    deal_hole_cards(hand)
    play(hand, (1, CALL), (2, CALL), (3, CHECK))
    assert middle_pot(hand) == sum(hand_player.total_contribution for hand_player in hand.players) == 30
    assert pots(hand) == (pot(30, 1, 2, 3),)


# =============================================================================
# POT LAYERS
# =============================================================================


def test_folded_chips_are_dead_money_in_every_layer_they_reach(make_hand: HandFactory) -> None:
    """Seat 1 is live with 100, seat 2 folded with 150 and seat 3 is live with 150. The folded 150 count in the middle
    pot and in both layers they reach, but seat 2 is eligible for neither: the side pot is seat 2's 50 between 100
    and 150 and seat 3's matching 50."""
    hand = collected_hand(make_hand, {1: 100, 2: 150, 3: 150}, folded={2})

    assert middle_pot(hand) == 400
    assert pots(hand) == (pot(300, 1, 3), pot(100, 3))


def test_folded_contribution_adds_a_layer_without_changing_the_eligible_seats(make_hand: HandFactory) -> None:
    """Seats 1 and 2 are live with 200 each and seat 3 folded with 150. The folded 150 still mark a layer boundary, so
    the two layers stay separate even though the same seats are eligible for both."""
    hand = collected_hand(make_hand, {1: 200, 2: 200, 3: 150}, folded={3})

    assert pots(hand) == (pot(450, 1, 2), pot(100, 1, 2))


def test_all_in_players_are_eligible_for_every_layer_they_reach(make_hand: HandFactory) -> None:
    """Seat 1 is all-in for 50, seat 2 all-in for 120, and seats 3 and 4 are live with 300 each: each all-in player
    is eligible for the main pot and every side pot up to its own contribution, and for none above it."""
    hand = collected_hand(make_hand, {1: 50, 2: 120, 3: 300, 4: 300}, all_in={1, 2})

    assert pots(hand) == (pot(200, 1, 2, 3, 4), pot(210, 2, 3, 4), pot(360, 3, 4))


def test_every_distinct_contribution_level_makes_its_own_layer(make_hand: HandFactory) -> None:
    """Nine-handed, the collected contributions are 100, 200, ..., 800 and 800, nobody folded. Each of the eight
    distinct levels makes one layer: the main pot of 900 and seven side pots of 800 down to 200, with 9 down to 2
    eligible seats, the deepest layering a collected nine-handed hand can have."""
    contributions = {seat_number: 100 * seat_number for seat_number in range(1, 9)} | {9: 800}
    hand = collected_hand(make_hand, contributions)

    layers = pots(hand)
    assert [layer.amount for layer in layers] == [900, 800, 700, 600, 500, 400, 300, 200]
    assert [layer.eligible_seats for layer in layers] == [frozenset(range(level, 10)) for level in range(1, 9)]
