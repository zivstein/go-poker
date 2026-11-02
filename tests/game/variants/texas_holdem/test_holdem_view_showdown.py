"""The Hold'em player view across the showdown paths: what is shown, mucked, folded or won unshown (ADR 0005 §3).

Hands are played through the real `HoldemGame` from decks stacked with the shared `queue_decks` and `draw_order`
fixtures. Blinds are 5/10. The board is 2c 7d 9h Jc Ks. Seat 1 (the button) holds a pair of aces, seat 2 (the small
blind) a set of kings, seat 3 (the big blind) king high and the fourth seat of the all-in hand a pair of queens. After
the flop the small blind acts first, so a check-down decides in the order 2, 3, 1 and the interactive showdown starts
with seat 2.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, fields, is_dataclass
from typing import Any

from go_poker.core.card import Card
from go_poker.core.hand_rank import HandRank
from go_poker.game.betting.actions import Action, ActionType
from go_poker.game.betting.stakes import Stakes
from go_poker.game.player import Player, PlayerStatus
from go_poker.game.poker_hand import PokerHand
from go_poker.game.showdown import ShowdownAction, ShowdownKind
from go_poker.game.table import Table
from go_poker.game.variants.texas_holdem.game import HoldemGame
from go_poker.game.variants.texas_holdem.hand_strength import hand_strength
from go_poker.game.variants.texas_holdem.view import HandView, ParticipantView, holdem_view
from go_poker.game.visibility import HandSettledView, ShowdownDecidedView

STAKES = Stakes(small_blind=5, big_blind=10)
FOLD = Action(ActionType.FOLD)
CHECK = Action(ActionType.CHECK)
CALL = Action(ActionType.CALL)
SHOW = ShowdownAction.SHOW
MUCK = ShowdownAction.MUCK

HOLES = {1: "Ah Ad", 2: "Kd Kh", 3: "3s 4s"}
ALL_IN_HOLES = {**HOLES, 4: "Qh Qd"}
BOARD = "2c 7d 9h Jc Ks"
VIEWERS = [None, 1, 2, 3, 4, 6]

type DrawOrder = Callable[..., list[Card]]
type QueueDecks = Callable[..., Any]
type Cards = Callable[[str], list[Card]]
type Play = tuple[int, Action | ShowdownAction]

LIMP: tuple[Play, ...] = ((1, CALL), (2, CALL), (3, CHECK))
STREET_CHECKS: tuple[Play, ...] = ((2, CHECK), (3, CHECK), (1, CHECK))
TO_SHOWDOWN: tuple[Play, ...] = (*LIMP, *STREET_CHECKS, *STREET_CHECKS, *STREET_CHECKS)
# Seat 3 bets and folds on the flop, so the showdown is between seats 2 and 1, in that order.
FLOP_FOLD_TO_SHOWDOWN: tuple[Play, ...] = (
    *LIMP,
    (2, Action(ActionType.BET, 20)),
    (3, FOLD),
    (1, CALL),
    (2, CHECK),
    (1, CHECK),
    (2, CHECK),
    (1, CHECK),
)
# Everyone but the folder is all-in preflop with 100 chips.
ALL_IN_PLAYS: tuple[Play, ...] = (
    (4, FOLD),
    (1, Action(ActionType.RAISE, 100)),
    (2, CALL),
    (3, CALL),
)


@dataclass
class Setup:
    game: HoldemGame
    table: Table

    @property
    def hand(self) -> PokerHand:
        assert self.game.hand is not None
        return self.game.hand

    def play(self, *plays: Play) -> None:
        for seat, action in plays:
            self.game.act(seat, action)

    def view(self, viewer: int | None) -> HandView:
        hand_view = holdem_view(self.table, self.game.hand, viewer).hand
        assert hand_view is not None
        return hand_view


def new_game(
    queue_decks: QueueDecks,
    draw_order: DrawOrder,
    *plays: Play,
    holes: dict[int, str] = HOLES,
    stack: int = 1000,
) -> Setup:
    table = Table(9)
    for seat in holes:
        table.sit_in(Player(f"P{seat}", stack=stack), seat)
    queue_decks(draw_order(holes, BOARD, 1))
    game = HoldemGame(table, STAKES)
    game.start(lambda _seats: 1)
    setup = Setup(game, table)
    setup.play(*plays)
    return setup


def participant(view: HandView, seat: int) -> ParticipantView:
    return next(entry for entry in view.participants if entry.seat == seat)


def reachable(value: object) -> Iterator[object]:
    yield value
    if is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            yield from reachable(getattr(value, field.name))
    elif isinstance(value, tuple | list | set | frozenset):
        for item in value:
            yield from reachable(item)


def assert_nothing_but_visible_facts(setup: Setup, holes: dict[int, str], cards: Cards) -> None:
    """For every viewer, the cards and hand ranks in its view belong to the board, its own seat or a shown seat."""
    hand = setup.hand
    shown = set(hand.showdown.shown) if hand.showdown is not None else set()
    for viewer in (*VIEWERS, 5):
        visible = shown | ({viewer} if viewer in holes else set())
        view = holdem_view(setup.table, hand, viewer)
        assert not any(isinstance(item, PlayerStatus) for item in reachable(view))
        found_cards = {item for item in reachable(view) if isinstance(item, Card)}
        allowed_cards = set(hand.board) | {card for seat in visible for card in cards(holes[seat])}
        assert found_cards <= allowed_cards, f"viewer {viewer} sees a card it must not"

        found_ranks = {item for item in reachable(view) if isinstance(item, HandRank)}
        strengths = (hand_strength(hand, seat) for seat in visible)
        allowed_ranks = {strength.rank for strength in strengths if strength is not None}
        assert found_ranks <= allowed_ranks, f"viewer {viewer} sees a rank it must not"


# =============================================================================
# INTERACTIVE SHOW
# =============================================================================


def test_a_shown_hand_is_public_with_its_cards_and_strength(
    queue_decks: QueueDecks, draw_order: DrawOrder, cards: Cards
) -> None:
    setup = new_game(queue_decks, draw_order, *TO_SHOWDOWN, (2, SHOW))

    for viewer in (None, 1, 3, 6):
        shown = participant(setup.view(viewer), 2)
        assert shown.hole_cards == tuple(cards(HOLES[2]))
        assert shown.strength == hand_strength(setup.hand, 2)
        assert shown.strength is not None and shown.has_live_cards
    assert setup.view(None).showdown == setup.hand.showdown
    assert_nothing_but_visible_facts(setup, HOLES, cards)


def test_seats_that_have_not_shown_stay_hidden_during_the_showdown(
    queue_decks: QueueDecks, draw_order: DrawOrder, cards: Cards
) -> None:
    setup = new_game(queue_decks, draw_order, *TO_SHOWDOWN, (2, SHOW))

    for viewer in (None, 2, 6):
        for seat in (1, 3):
            hidden = participant(setup.view(viewer), seat)
            assert hidden.hole_cards is None and hidden.strength is None and hidden.has_live_cards
    assert participant(setup.view(3), 3).hole_cards == tuple(cards(HOLES[3]))


def test_a_settled_show_publishes_the_shown_ranks_and_hides_the_muck(
    queue_decks: QueueDecks, draw_order: DrawOrder, cards: Cards
) -> None:
    setup = new_game(queue_decks, draw_order, *TO_SHOWDOWN, (2, SHOW), (3, SHOW), (1, MUCK))
    hand = setup.hand
    assert hand.settlement is not None

    for viewer in (None, 6):
        view = setup.view(viewer)
        assert view.settlement is not None
        assert [seat for seat, _ in view.settlement.showdown_ranks] == [2, 3]
        for seat, rank in view.settlement.showdown_ranks:
            strength = participant(view, seat).strength
            assert strength is not None and strength.rank == rank
        assert participant(view, 1).hole_cards is None and participant(view, 1).strength is None
        assert not participant(view, 1).has_live_cards
    assert_nothing_but_visible_facts(setup, HOLES, cards)


# =============================================================================
# INTERACTIVE MUCK
# =============================================================================


def test_a_mucked_hand_is_private_to_others_and_visible_to_its_owner(
    queue_decks: QueueDecks, draw_order: DrawOrder, cards: Cards
) -> None:
    setup = new_game(queue_decks, draw_order, *TO_SHOWDOWN, (2, MUCK))

    owner = participant(setup.view(2), 2)
    assert owner.hole_cards == tuple(cards(HOLES[2]))
    assert owner.strength == hand_strength(setup.hand, 2)
    assert not owner.has_live_cards
    for viewer in (None, 1, 3, 6):
        other = participant(setup.view(viewer), 2)
        assert other.hole_cards is None and other.strength is None and not other.has_live_cards
    assert_nothing_but_visible_facts(setup, HOLES, cards)


def test_a_mucked_hand_stays_private_after_settlement(
    queue_decks: QueueDecks, draw_order: DrawOrder, cards: Cards
) -> None:
    setup = new_game(queue_decks, draw_order, *TO_SHOWDOWN, (2, MUCK), (3, SHOW), (1, MUCK))
    assert setup.hand.settlement is not None

    view = setup.view(None)

    assert view.settlement is not None
    assert [seat for seat, _ in view.settlement.showdown_ranks] == [3]
    assert participant(view, 2).hole_cards is None
    assert participant(view, 3).hole_cards == tuple(cards(HOLES[3]))
    assert participant(setup.view(2), 2).hole_cards == tuple(cards(HOLES[2]))
    assert_nothing_but_visible_facts(setup, HOLES, cards)


# =============================================================================
# ALL-IN SHOWDOWN
# =============================================================================


def test_an_all_in_showdown_reveals_every_live_seat_and_hides_the_folded_one(
    queue_decks: QueueDecks, draw_order: DrawOrder, cards: Cards
) -> None:
    setup = new_game(queue_decks, draw_order, *ALL_IN_PLAYS, holes=ALL_IN_HOLES, stack=100)
    hand = setup.hand
    assert hand.showdown is not None and hand.showdown.kind is ShowdownKind.ALL_IN

    for viewer in (None, 1, 2, 3, 6):
        view = setup.view(viewer)
        for seat in (1, 2, 3):
            entry = participant(view, seat)
            assert entry.hole_cards == tuple(cards(ALL_IN_HOLES[seat]))
            assert entry.strength == hand_strength(hand, seat)
        folded = participant(view, 4)
        assert folded.folded and not folded.has_live_cards
        assert folded.hole_cards is None and folded.strength is None
    assert participant(setup.view(4), 4).hole_cards == tuple(cards(ALL_IN_HOLES[4]))
    assert_nothing_but_visible_facts(setup, ALL_IN_HOLES, cards)


def test_an_all_in_settlement_ranks_exactly_the_live_seats(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order, *ALL_IN_PLAYS, holes=ALL_IN_HOLES, stack=100)

    view = setup.view(None)

    assert view.settlement is not None
    assert [seat for seat, _ in view.settlement.showdown_ranks] == [1, 2, 3]
    assert [entry.has_live_cards for entry in view.participants] == [True, True, True, False]


# =============================================================================
# NO SHOWDOWN, LAST CONTENDER, FOLDS
# =============================================================================


def test_an_uncontested_win_keeps_the_winners_cards_hidden_and_has_no_ranks(
    queue_decks: QueueDecks, draw_order: DrawOrder, cards: Cards
) -> None:
    setup = new_game(queue_decks, draw_order, *LIMP, (2, Action(ActionType.BET, 20)), (3, FOLD), (1, FOLD))
    assert setup.hand.showdown is None

    for viewer in (None, 1, 3, 6):
        view = setup.view(viewer)
        winner = participant(view, 2)
        assert winner.hole_cards is None and winner.strength is None and winner.has_live_cards
        assert view.showdown is None
        assert view.settlement is not None and view.settlement.showdown_ranks == ()
    owner = participant(setup.view(2), 2)
    assert owner.hole_cards == tuple(cards(HOLES[2])) and owner.strength == hand_strength(setup.hand, 2)
    assert_nothing_but_visible_facts(setup, HOLES, cards)


def test_a_last_contender_who_is_never_asked_wins_unshown(
    queue_decks: QueueDecks, draw_order: DrawOrder, cards: Cards
) -> None:
    setup = new_game(queue_decks, draw_order, *TO_SHOWDOWN, (2, MUCK), (3, MUCK))
    assert setup.hand.showdown is not None and setup.hand.showdown.shown == ()

    for viewer in (None, 2, 3, 6):
        view = setup.view(viewer)
        last = participant(view, 1)
        assert last.hole_cards is None and last.strength is None and last.has_live_cards
        assert view.settlement is not None and view.settlement.showdown_ranks == ()
        decisions = [event for event in view.log if isinstance(event, ShowdownDecidedView)]
        assert [event.seat for event in decisions] == [2, 3]
    assert participant(setup.view(1), 1).hole_cards == tuple(cards(HOLES[1]))
    assert_nothing_but_visible_facts(setup, HOLES, cards)


def test_folded_cards_stay_hidden_after_settlement(
    queue_decks: QueueDecks, draw_order: DrawOrder, cards: Cards
) -> None:
    setup = new_game(queue_decks, draw_order, *FLOP_FOLD_TO_SHOWDOWN, (2, SHOW), (1, MUCK))
    assert setup.hand.settlement is not None

    for viewer in (None, 1, 2, 6):
        folded = participant(setup.view(viewer), 3)
        assert folded.folded and not folded.has_live_cards
        assert folded.hole_cards is None and folded.strength is None
    assert participant(setup.view(3), 3).hole_cards == tuple(cards(HOLES[3]))
    assert_nothing_but_visible_facts(setup, HOLES, cards)


def test_the_projected_settlement_never_names_an_unshown_seats_rank(
    queue_decks: QueueDecks, draw_order: DrawOrder
) -> None:
    setup = new_game(queue_decks, draw_order, *TO_SHOWDOWN, (2, MUCK), (3, SHOW), (1, SHOW))
    hand = setup.hand
    assert hand.showdown is not None and hand.showdown.mucked == (2,)
    mucked_rank = hand_strength(hand, 2)
    assert mucked_rank is not None

    for viewer in VIEWERS:
        view = setup.view(viewer)
        assert view.settlement is not None
        assert [seat for seat, _ in view.settlement.showdown_ranks] == [1, 3]
        assert mucked_rank.rank not in {rank for _, rank in view.settlement.showdown_ranks}
        assert (participant(view, 2).strength is not None) == (viewer == 2)


def test_the_log_ends_with_the_shared_projected_settlement(queue_decks: QueueDecks, draw_order: DrawOrder) -> None:
    setup = new_game(queue_decks, draw_order, *TO_SHOWDOWN, (2, SHOW), (3, MUCK), (1, MUCK))

    for viewer in VIEWERS:
        view = setup.view(viewer)
        assert view.settlement is not None
        assert view.log[-1] == HandSettledView(view.settlement)
