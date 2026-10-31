"""End-to-end Hold'em hands driven only by `begin_hand`, `act` and `current_actor`.

Nobody collects, deals, starts a round or a showdown, or settles: every call must leave the hand settled, waiting for a
betting actor who has something to do, or waiting for a showdown decider. `Run` checks that after every call (see
`assert_postcondition`). Each scenario then asserts the exact payouts, the final stacks, the seats whose hands were
ranked and that the chips on the table are conserved.

Hands come from the shared `stacked_hand` fixture. Unless said otherwise there are three seats, the button (1), the
small blind (2) and the big blind (3), with blinds 5/10 and 1000 chips each; preflop seat 1 acts first and on every
later street seat 2 does. Hole cards are chosen by strength on DRY_BOARD, which holds no pair and no possible flush, and
whose only possible straight (7-8-9-T-J) needs an eight and a ten no scenario deals: AA beats KK, which beats 3s 4s (a
pair of fours), which beats 5s 6s (jack high).
"""

from collections.abc import Callable

from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.legal_actions import NOTHING_LEGAL, legal_actions
from go_poker.game.betting.pots import Pot, pots
from go_poker.game.betting.stakes import Stakes
from go_poker.game.game_lifecycle import start_game
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.showdown import ShowdownAction, ShowdownKind
from go_poker.game.street import Street
from go_poker.game.table import Table
from go_poker.game.variants.texas_holdem.hand_flow import act, begin_hand, current_actor

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
SHOW = ShowdownAction.SHOW
MUCK = ShowdownAction.MUCK

DRY_BOARD = "2c 4d 7h 9s Jc"
HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
HOLES_4 = {1: "Qh Qd", 2: "Ah Ad", 3: "Kd Kh", 4: "5s 6s"}

BURNED_BY_RIVER = 3
DECK_AFTER_FULL_BOARD = 52 - 2 * 3 - BURNED_BY_RIVER - 5

type StackedHand = Callable[..., PokerHand]
type Move = tuple[int, Action | ShowdownAction]


def bet(target: int) -> Action:
    return Action(ActionType.BET, target)


def raise_to(target: int) -> Action:
    return Action(ActionType.RAISE, target)


def assert_postcondition(hand: PokerHand) -> None:
    """After a call the hand is settled, or a betting actor has something to do, or a showdown decider is waiting."""
    if hand.settlement is not None:
        assert current_actor(hand) is None
        return
    betting = hand.betting
    assert betting is not None
    if betting.current_actor is not None:
        assert current_actor(hand) == betting.current_actor
        assert legal_actions(hand) != NOTHING_LEGAL
        return
    showdown = hand.showdown
    assert showdown is not None
    assert not showdown.is_complete
    assert showdown.current_decider is not None
    assert current_actor(hand) == showdown.current_decider


def hand_pots(hand: PokerHand) -> list[Pot]:
    return list(pots(hand))


def ranked_seats(hand: PokerHand) -> set[int]:
    assert hand.settlement is not None
    return {seat for seat, _ in hand.settlement.showdown_ranks}


class Run:
    """One hand driven through `hand_flow`, checking the postcondition after every call."""

    def __init__(self, hand: PokerHand, stakes: Stakes = STAKES) -> None:
        self.hand = hand
        self.stakes = stakes
        self.total_chips = sum(state.player.stack for state in hand.players)

    def begin(self) -> Run:
        begin_hand(self.hand, self.stakes)
        assert_postcondition(self.hand)
        return self

    def play(self, *moves: Move) -> Run:
        for seat, action in moves:
            assert current_actor(self.hand) == seat  # the hand really waits for this seat
            act(self.hand, seat, action)
            assert_postcondition(self.hand)
        return self

    def stacks(self) -> dict[int, int]:
        return {state.seat_number: state.player.stack for state in self.hand.players}

    def assert_settled(self, stacks: dict[int, int], payouts: dict[int, int], ranked: set[int]) -> None:
        """Settled with exactly these final stacks and payouts, ranking exactly these seats, conserving the chips."""
        assert self.hand.settlement is not None
        assert self.stacks() == stacks
        assert self.hand.settlement.payouts == payouts
        assert ranked_seats(self.hand) == ranked
        assert sum(self.stacks().values()) == self.total_chips
        assert current_actor(self.hand) is None


def started(stacked_hand: StackedHand, holes: dict[int, str] = HOLES, **kwargs: object) -> Run:
    return Run(stacked_hand(holes, DRY_BOARD, **kwargs)).begin()


def preflop_limp(run: Run) -> Run:
    """Seats 1 and 2 call and seat 3 checks: 30 in the pot and the flop dealt."""
    return run.play((1, CALL), (2, CALL), (3, CHECK))


def check_street(run: Run) -> Run:
    return run.play((2, CHECK), (3, CHECK), (1, CHECK))


def at_river(run: Run) -> Run:
    """Check the hand down to the start of the river round, with seat 2 to act."""
    preflop_limp(run)
    check_street(run)
    check_street(run)
    assert run.hand.street is Street.RIVER and current_actor(run.hand) == 2
    return run


# =============================================================================
# 1-3. INTERACTIVE RIVER SHOWDOWNS
# =============================================================================


def test_river_showdown_where_everyone_shows_pays_the_best_hand(stacked_hand: StackedHand) -> None:
    """Seat 3 bets the river and seats 1 and 2 call, so the decision order starts with seat 3. All three show."""
    run = started(stacked_hand)
    at_river(run)
    assert run.hand.showdown is None

    run.play((2, CHECK), (3, bet(20)), (1, CALL), (2, CALL))

    showdown = run.hand.showdown
    assert showdown is not None and showdown.kind is ShowdownKind.INTERACTIVE
    assert showdown.order == (3, 1, 2)
    run.play((3, SHOW), (1, SHOW), (2, SHOW))
    # Everybody put in 30 (the limped 10 and a river bet of 20): 90 chips go to seat 1's aces.
    run.assert_settled({1: 1060, 2: 970, 3: 970}, {1: 90}, {1, 2, 3})
    assert run.hand.showdown is not None and run.hand.showdown.shown == (3, 1, 2)


def test_river_showdown_with_a_muck_pays_the_best_remaining_shown_hand(stacked_hand: StackedHand) -> None:
    """Checked down, seat 2 decides first. Seat 1 mucks the best hand without showing, so seat 2's kings beat seat 3."""
    run = started(stacked_hand)
    at_river(run)

    run.play((2, CHECK), (3, CHECK), (1, CHECK))
    assert run.hand.showdown is not None and run.hand.showdown.order == (2, 3, 1)
    run.play((2, SHOW), (3, SHOW), (1, MUCK))

    run.assert_settled({1: 990, 2: 1020, 3: 990}, {2: 30}, {2, 3})
    assert run.hand.showdown is not None and run.hand.showdown.mucked == (1,)


def test_river_showdown_where_the_loser_mucks_ranks_only_the_shown_hands(stacked_hand: StackedHand) -> None:
    run = started(stacked_hand)
    at_river(run)

    run.play((2, CHECK), (3, CHECK), (1, CHECK), (2, SHOW), (3, MUCK), (1, SHOW))

    run.assert_settled({1: 1020, 2: 990, 3: 990}, {1: 30}, {1, 2})
    assert run.hand.showdown is not None and run.hand.showdown.mucked == (3,)


def test_two_mucks_leave_the_last_contender_the_winner_without_a_decision_or_a_rank(stacked_hand: StackedHand) -> None:
    run = started(stacked_hand)
    at_river(run)
    run.play((2, CHECK), (3, CHECK), (1, CHECK))
    assert run.hand.showdown is not None and run.hand.showdown.order == (2, 3, 1)

    run.play((2, MUCK))
    assert run.hand.settlement is None and current_actor(run.hand) == 3
    run.play((3, MUCK))

    # Seat 1 is not asked to decide and wins without showing.
    run.assert_settled({1: 1020, 2: 990, 3: 990}, {1: 30}, set())
    assert run.hand.showdown is not None and run.hand.showdown.contenders == (1,)


def test_heads_up_first_muck_gives_the_pot_to_the_other_player(stacked_hand: StackedHand) -> None:
    """Heads-up the button (1) is the small blind and the big blind (2) decides first on the river."""
    run = started(stacked_hand, {1: "Ah Ad", 2: "Kd Kh"})
    run.play((1, CALL), (2, CHECK))
    for _ in range(3):
        run.play((2, CHECK), (1, CHECK))
    assert run.hand.showdown is not None and run.hand.showdown.order == (2, 1)

    run.play((2, MUCK))

    run.assert_settled({1: 1010, 2: 990}, {1: 20}, set())


def test_river_aggressor_decides_first_and_a_late_muck_is_not_paid(stacked_hand: StackedHand) -> None:
    run = started(stacked_hand)
    at_river(run)

    run.play((2, bet(50)), (3, raise_to(150)), (1, CALL), (2, CALL))
    assert run.hand.showdown is not None and run.hand.showdown.order == (3, 1, 2)
    run.play((3, SHOW), (1, SHOW), (2, MUCK))

    # Everybody put in 160 (the limped 10 and a river bet of 150): seat 1's aces win
    # all 480.
    run.assert_settled({1: 1320, 2: 840, 3: 840}, {1: 480}, {1, 3})


# =============================================================================
# 4. FOLD-OUTS
# =============================================================================


def test_folds_on_the_preflop_settle_the_big_blind_at_once(stacked_hand: StackedHand) -> None:
    run = started(stacked_hand)

    run.play((1, FOLD), (2, FOLD))

    run.assert_settled({1: 1000, 2: 995, 3: 1005}, {3: 10}, set())
    assert run.hand.showdown is None and run.hand.board == []


def test_folds_on_each_later_street_settle_at_once_without_a_showdown(stacked_hand: StackedHand) -> None:
    for street, board_size in ((Street.FLOP, 3), (Street.TURN, 4), (Street.RIVER, 5)):
        run = started(stacked_hand)
        preflop_limp(run)
        while run.hand.street is not street:
            check_street(run)
        assert run.hand.settlement is None

        run.play((2, bet(20)), (3, FOLD), (1, FOLD))

        # Seat 2 wins the 30 chips of the limped pot; its unmatched bet goes back.
        run.assert_settled({1: 990, 2: 1020, 3: 990}, {2: 30}, set())
        assert run.hand.showdown is None
        assert len(run.hand.board) == board_size and run.hand.street is street


def test_a_fold_that_leaves_one_player_settles_before_the_remaining_players_act(stacked_hand: StackedHand) -> None:
    run = started(stacked_hand)
    preflop_limp(run)

    run.play((2, bet(20)), (3, raise_to(60)), (1, FOLD), (2, FOLD))

    run.assert_settled({1: 990, 2: 970, 3: 1040}, {3: 70}, set())


# =============================================================================
# 5-7. ALL-INS
# =============================================================================


def test_preflop_all_in_runs_the_board_out_without_starting_a_betting_round(stacked_hand: StackedHand) -> None:
    run = started(stacked_hand)

    run.play((1, raise_to(1000)), (2, CALL), (3, CALL))

    run.assert_settled({1: 3000, 2: 0, 3: 0}, {1: 3000}, {1, 2, 3})
    hand = run.hand
    assert hand.street is Street.RIVER and len(hand.board) == 5
    assert hand.betting is not None and hand.betting.street is Street.PREFLOP  # no meaningless rounds were started
    assert len(hand.burned_cards) == BURNED_BY_RIVER and len(hand.deck) == DECK_AFTER_FULL_BOARD
    assert hand.showdown is not None
    assert (hand.showdown.kind, hand.showdown.order, hand.showdown.is_complete) == (
        ShowdownKind.ALL_IN,
        (2, 3, 1),
        True,
    )


def test_preflop_all_in_tables_only_the_live_seats(stacked_hand: StackedHand) -> None:
    run = started(stacked_hand)

    run.play((1, raise_to(1000)), (2, FOLD), (3, CALL))

    run.assert_settled({1: 2005, 2: 995, 3: 0}, {1: 2005}, {1, 3})
    assert run.hand.showdown is not None and run.hand.showdown.order == (3, 1)
    assert run.hand.betting is not None and run.hand.betting.street is Street.PREFLOP


def test_flop_all_in_deals_only_the_remaining_streets(stacked_hand: StackedHand) -> None:
    run = started(stacked_hand)
    preflop_limp(run)
    assert len(run.hand.board) == 3 and len(run.hand.burned_cards) == 1

    run.play((2, bet(990)), (3, CALL), (1, CALL))

    run.assert_settled({1: 3000, 2: 0, 3: 0}, {1: 3000}, {1, 2, 3})
    hand = run.hand
    assert hand.street is Street.RIVER and len(hand.board) == 5
    assert hand.betting is not None and hand.betting.street is Street.FLOP
    assert len(hand.burned_cards) == BURNED_BY_RIVER and len(hand.deck) == DECK_AFTER_FULL_BOARD


def test_turn_all_in_deals_only_the_river(stacked_hand: StackedHand) -> None:
    run = started(stacked_hand)
    preflop_limp(run)
    check_street(run)
    assert len(run.hand.board) == 4 and len(run.hand.burned_cards) == 2

    run.play((2, bet(990)), (3, CALL), (1, CALL))

    run.assert_settled({1: 3000, 2: 0, 3: 0}, {1: 3000}, {1, 2, 3})
    hand = run.hand
    assert hand.street is Street.RIVER and len(hand.board) == 5
    assert hand.betting is not None and hand.betting.street is Street.TURN
    assert len(hand.burned_cards) == BURNED_BY_RIVER and len(hand.deck) == DECK_AFTER_FULL_BOARD


def test_river_all_in_settles_with_an_all_in_showdown_and_no_decisions(stacked_hand: StackedHand) -> None:
    run = started(stacked_hand)
    at_river(run)

    run.play((2, bet(990)), (3, CALL), (1, CALL))

    run.assert_settled({1: 3000, 2: 0, 3: 0}, {1: 3000}, {1, 2, 3})
    assert run.hand.showdown is not None and run.hand.showdown.kind is ShowdownKind.ALL_IN


def test_several_all_in_levels_award_each_side_pot_to_its_own_winner(stacked_hand: StackedHand) -> None:
    """Seat 4 raises to 1000 over three shorter stacks that call all-in. Seat 4's unmatched 700 goes back, and it still
    has chips when betting closes. The aces of the shortest stack win the main pot, the kings the next, the queens the
    last; seat 4's high card wins nothing."""
    run = started(stacked_hand, HOLES_4, stacks={1: 300, 2: 100, 3: 200, 4: 1000})

    run.play((4, raise_to(1000)), (1, CALL), (2, CALL), (3, CALL))

    run.assert_settled({1: 200, 2: 400, 3: 300, 4: 700}, {2: 400, 3: 300, 1: 200}, {1, 2, 3, 4})
    assert hand_pots(run.hand) == [
        Pot(400, frozenset({1, 2, 3, 4})),
        Pot(300, frozenset({1, 3, 4})),
        Pot(200, frozenset({1, 4})),
    ]
    assert run.hand.showdown is not None and run.hand.showdown.kind is ShowdownKind.ALL_IN


def test_a_player_with_chips_facing_an_all_in_goes_to_an_all_in_showdown(stacked_hand: StackedHand) -> None:
    """Seat 2 is all-in on the flop and seat 3, who still has chips, calls: nobody can bet, so the board runs out."""
    run = started(stacked_hand, stacks={1: 1000, 2: 100, 3: 1000})
    preflop_limp(run)

    run.play((2, bet(90)), (3, CALL), (1, FOLD))

    run.assert_settled({1: 990, 2: 210, 3: 900}, {2: 210}, {2, 3})
    assert run.hand.showdown is not None and run.hand.showdown.order == (2, 3)
    assert [pot.amount for pot in hand_pots(run.hand)] == [30, 180]
    assert run.hand.betting is not None and run.hand.betting.street is Street.FLOP


# =============================================================================
# 8-9. ORDINARY BETTING
# =============================================================================


def test_several_betting_rounds_with_raises_and_calls_end_in_an_interactive_showdown(stacked_hand: StackedHand) -> None:
    run = started(stacked_hand)

    # Preflop: seat 1 raises, seat 2 calls, seat 3 re-raises, seat 1 calls and seat 2 folds its 30.
    run.play((1, raise_to(30)), (2, CALL), (3, raise_to(90)), (1, CALL), (2, FOLD))
    assert run.hand.street is Street.FLOP and current_actor(run.hand) == 3
    # Flop: seat 3 bets, seat 1 raises, seat 3 calls.
    run.play((3, bet(60)), (1, raise_to(180)), (3, CALL))
    assert run.hand.street is Street.TURN and current_actor(run.hand) == 3
    # Turn: seat 3 checks, seat 1 bets, seat 3 calls.
    run.play((3, CHECK), (1, bet(100)), (3, CALL))
    assert run.hand.street is Street.RIVER and current_actor(run.hand) == 3
    # River: checked down.
    run.play((3, CHECK), (1, CHECK))
    assert run.hand.showdown is not None and run.hand.showdown.order == (3, 1)
    run.play((3, SHOW), (1, SHOW))

    # Seats 1 and 3 put in 370 each and seat 2 put in 30: 770 chips go to seat 1's aces.
    run.assert_settled({1: 1400, 2: 970, 3: 630}, {1: 770}, {1, 3})


def test_check_through_streets_deal_and_start_every_round_automatically(stacked_hand: StackedHand) -> None:
    run = started(stacked_hand)
    hand = run.hand

    preflop_limp(run)
    assert (hand.street, len(hand.board), len(hand.burned_cards), current_actor(hand)) == (Street.FLOP, 3, 1, 2)
    check_street(run)
    assert (hand.street, len(hand.board), len(hand.burned_cards), current_actor(hand)) == (Street.TURN, 4, 2, 2)
    check_street(run)
    assert (hand.street, len(hand.board), len(hand.burned_cards), current_actor(hand)) == (Street.RIVER, 5, 3, 2)
    assert hand.showdown is None
    check_street(run)

    assert hand.showdown is not None and hand.showdown.order == (2, 3, 1) and current_actor(hand) == 2
    run.play((2, SHOW), (3, SHOW), (1, SHOW))
    run.assert_settled({1: 1020, 2: 990, 3: 990}, {1: 30}, {1, 2, 3})


# =============================================================================
# 10-11. BLINDS ALONE AND THE LIFECYCLE
# =============================================================================


def test_blinds_alone_can_complete_the_hand_inside_begin_hand(stacked_hand: StackedHand) -> None:
    """Heads-up, both blinds are posted all-in (the big blind's extra 5 goes back), so nobody ever acts."""
    hand = stacked_hand({1: "Ah Ad", 2: "Kd Kh"}, DRY_BOARD, stacks={1: 5, 2: 10})
    run = Run(hand)

    begin_hand(hand, STAKES)
    assert_postcondition(hand)

    run.assert_settled({1: 10, 2: 5}, {1: 10}, {1, 2})
    assert hand.street is Street.RIVER and len(hand.board) == 5
    assert hand.showdown is not None and hand.showdown.kind is ShowdownKind.ALL_IN
    assert hand.betting is not None and hand.betting.street is Street.PREFLOP


def test_a_hand_from_the_game_lifecycle_is_driven_to_settlement() -> None:
    table = Table(max_seats=6)
    for seat in (2, 4, 5):
        table.sit_in(Player(f"P{seat}", stack=1000, status=PlayerStatus.WAITING), seat)
    hand = start_game(table, lambda seats: seats[0])  # the lifecycle's own shuffled deck
    run = Run(hand).begin()
    assert [state.seat_number for state in hand.players] == [2, 4, 5]

    # Everybody calls or checks, then shows at the river, whatever the cards turn out to be.
    for _ in range(100):
        seat = current_actor(hand)
        if seat is None:
            break
        if hand.showdown is not None:
            run.play((seat, SHOW))
        else:
            run.play((seat, CHECK if legal_actions(hand).can_check else CALL))
    else:
        raise AssertionError("the hand did not end")

    assert hand.settlement is not None
    assert hand.showdown is not None and hand.showdown.kind is ShowdownKind.INTERACTIVE
    assert ranked_seats(hand) == {2, 4, 5}
    payouts = hand.settlement.payouts
    assert sum(payouts.values()) == 30  # three players put in the big blind each
    assert run.stacks() == {seat: 990 + payouts.get(seat, 0) for seat in (2, 4, 5)}
    assert sum(run.stacks().values()) == run.total_chips == 3000
    assert len(hand.deck) == DECK_AFTER_FULL_BOARD


# =============================================================================
# 12. A SHORT STACK ALL-IN WHILE THE OTHERS KEEP BETTING
# =============================================================================


def mixed_all_in(stacked_hand: StackedHand) -> Run:
    """Seat 1 (A, 100 chips, aces) shoves preflop and seats 2 (B, 300, kings) and 3 (C, 300, a pair of fours) call. B
    and C still have 200 chips each, so the hand goes on between them."""
    run = started(stacked_hand, stacks={1: 100, 2: 300, 3: 300})
    run.play((1, raise_to(100)), (2, CALL), (3, CALL))
    return run


def assert_betting_goes_on_between_b_and_c(run: Run, street: Street) -> None:
    hand = run.hand
    assert hand.settlement is None and hand.showdown is None  # seat 1 being all-in does not start a showdown
    assert hand.street is street and hand.betting is not None and hand.betting.street is street
    assert current_actor(hand) in {2, 3}
    assert hand.players[0].all_in


def test_a_short_all_in_does_not_start_the_showdown_while_the_others_can_still_bet(stacked_hand: StackedHand) -> None:
    run = mixed_all_in(stacked_hand)

    assert_betting_goes_on_between_b_and_c(run, Street.FLOP)
    assert current_actor(run.hand) == 2 and len(run.hand.board) == 3

    run.play((2, bet(50)))
    assert_betting_goes_on_between_b_and_c(run, Street.FLOP)
    assert current_actor(run.hand) == 3
    run.play((3, CALL))
    assert_betting_goes_on_between_b_and_c(run, Street.TURN)
    assert current_actor(run.hand) == 2 and len(run.hand.board) == 4


def test_the_hand_goes_all_in_when_the_others_betting_closes_and_runs_the_board_out(stacked_hand: StackedHand) -> None:
    run = mixed_all_in(stacked_hand)
    run.play((2, bet(50)), (3, CALL))
    assert_betting_goes_on_between_b_and_c(run, Street.TURN)

    run.play((2, bet(150)))
    assert_betting_goes_on_between_b_and_c(run, Street.TURN)
    assert current_actor(run.hand) == 3
    run.play((3, CALL))

    # Everyone is all-in. The river is dealt without a betting round, and all three hands are tabled.
    hand = run.hand
    assert hand.street is Street.RIVER and len(hand.board) == 5
    assert hand.betting is not None and hand.betting.street is Street.TURN
    assert hand.showdown is not None
    assert (hand.showdown.kind, hand.showdown.order, hand.showdown.shown) == (
        ShowdownKind.ALL_IN,
        (2, 3, 1),
        (2, 3, 1),
    )
    # Seat 1 put in 100 and seats 2 and 3 put in 300: the aces win the 300 main pot and the kings the 400 side pot.
    assert hand_pots(hand) == [Pot(300, frozenset({1, 2, 3})), Pot(400, frozenset({2, 3}))]
    assert hand.settlement is not None
    assert [(award.pot, award.shares) for award in hand.settlement.pot_awards] == [
        (Pot(300, frozenset({1, 2, 3})), ((1, 300),)),
        (Pot(400, frozenset({2, 3})), ((2, 400),)),
    ]
    run.assert_settled({1: 300, 2: 400, 3: 0}, {1: 300, 2: 400}, {1, 2, 3})
    assert len(hand.burned_cards) == BURNED_BY_RIVER and len(hand.deck) == DECK_AFTER_FULL_BOARD


def test_the_hand_with_a_short_all_in_ends_in_an_all_in_showdown_when_the_others_check_down(
    stacked_hand: StackedHand,
) -> None:
    """When seats 2 and 3 only check, the river round completes with seat 1 all-in: still an ALL_IN showdown, with no
    decisions to make, not an interactive one."""
    run = mixed_all_in(stacked_hand)

    for street in (Street.FLOP, Street.TURN, Street.RIVER):
        assert_betting_goes_on_between_b_and_c(run, street)
        run.play((2, CHECK), (3, CHECK))

    hand = run.hand
    assert hand.showdown is not None and hand.showdown.kind is ShowdownKind.ALL_IN
    assert hand.showdown.order == (2, 3, 1)
    # Nobody bet after the shove, so there is one 300 pot, which seat 1's aces win.
    run.assert_settled({1: 300, 2: 200, 3: 200}, {1: 300}, {1, 2, 3})
