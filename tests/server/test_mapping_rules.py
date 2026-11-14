"""The mapping rules that are easiest to get wrong, each on its own (ADR 0009 §3, §10).

These are pure-function tests: the engine's frozen view values go in, wire models come out. The same rules are
exercised end to end over a real session in `test_mapping_snapshots.py`.
"""

from collections.abc import Sequence

import pytest

from go_poker.app.identity import DisplayName
from go_poker.app.views import SessionSeatView
from go_poker.core.best_hand import BestHand
from go_poker.core.card import Card, Rank, Suit
from go_poker.core.deck import Deck
from go_poker.core.hand_rank import HandCategory, HandRank
from go_poker.game.betting.pots import Pot
from go_poker.game.position import Blind, Position
from go_poker.game.showdown import Showdown, ShowdownAction, ShowdownKind
from go_poker.game.variants.texas_holdem.dealing import HOLE_CARD_COUNT
from go_poker.game.variants.texas_holdem.view import OccupantStatus, OccupantView, ParticipantView, SeatView
from go_poker.game.visibility import PotAwardView, SettlementView
from go_poker.server import mapping

ACE_OF_HEARTS = Card(Rank.ACE, Suit.HEARTS)
KING_OF_HEARTS = Card(Rank.KING, Suit.HEARTS)


def _participant(
    *,
    hole_cards: tuple[Card, ...] | None,
    has_live_cards: bool,
    folded: bool = False,
    position: Position = Position.BTN,
    blind: Blind = Blind.NONE,
) -> ParticipantView:
    return ParticipantView(
        seat=1,
        position=position,
        blind=blind,
        in_front=0,
        folded=folded,
        all_in=False,
        has_live_cards=has_live_cards,
        hole_cards=hole_cards,
        strength=None,
    )


# --- Cards (ADR 0009 §3) ---


def test_a_card_is_its_rank_character_then_its_suit_character() -> None:
    assert mapping.card(Card(Rank.TEN, Suit.HEARTS)) == "Th"
    assert mapping.card(ACE_OF_HEARTS) == "Ah"
    assert mapping.card(Card(Rank.TWO, Suit.CLUBS)) == "2c"


def test_the_whole_deck_maps_to_distinct_two_character_codes_with_no_engine_glyph() -> None:
    codes = [mapping.card(card) for card in Deck.create_new_deck()]
    assert len(set(codes)) == 52
    assert all(len(code) == 2 for code in codes)
    assert all(code[0] in "23456789TJQKA" and code[1] in "cdhs" for code in codes)


# --- Hidden cards (ADR 0009 §10) ---


@pytest.mark.parametrize(
    ("case", "participant", "expected"),
    [
        ("the viewer's own live cards", _participant(hole_cards=(ACE_OF_HEARTS,), has_live_cards=True), 0),
        ("a shown seat's cards", _participant(hole_cards=(ACE_OF_HEARTS, KING_OF_HEARTS), has_live_cards=True), 0),
        ("a hidden live hand", _participant(hole_cards=None, has_live_cards=True), HOLE_CARD_COUNT),
        ("the viewer's own folded cards", _participant(hole_cards=(ACE_OF_HEARTS,), has_live_cards=False), 0),
        ("another seat that folded", _participant(hole_cards=None, has_live_cards=False, folded=True), 0),
        ("another seat that mucked", _participant(hole_cards=None, has_live_cards=False), 0),
    ],
)
def test_the_hidden_card_count_is_the_backs_to_draw(case: str, participant: ParticipantView, expected: int) -> None:
    assert mapping.hidden_card_count(participant) == expected
    assert mapping.participant(participant).hidden_card_count == expected


def test_a_hidden_hand_counts_the_engines_hole_card_count_and_assumes_nothing() -> None:
    hidden = _participant(hole_cards=None, has_live_cards=True)
    assert mapping.hidden_card_count(hidden) == HOLE_CARD_COUNT


def test_the_hidden_count_is_read_from_the_engines_constant_and_is_not_a_literal_two(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ADR 0009 §10: `HOLE_CARD_COUNT` is the single source of the count, so a four-card variant needs no change here.

    Replacing the constant the mapper reads must change the count. A literal `2` in `hidden_card_count` would pass
    every other test, because today's constant *is* 2.
    """
    hidden = _participant(hole_cards=None, has_live_cards=True)
    monkeypatch.setattr(mapping, "HOLE_CARD_COUNT", 4)

    assert mapping.hidden_card_count(hidden) == 4
    assert mapping.participant(hidden).hidden_card_count == 4
    assert mapping.hidden_card_count(_participant(hole_cards=(ACE_OF_HEARTS,), has_live_cards=True)) == 0


# --- Enums (ADR 0009 §3) ---


def test_the_position_of_the_second_seat_under_the_gun_is_utg1() -> None:
    assert mapping.POSITIONS[Position.UTG1] == "utg1"
    assert mapping.POSITIONS[Position.UTG1] != Position.UTG1.value
    assert mapping.participant(_participant(hole_cards=None, has_live_cards=True, position=Position.UTG1)).position == (
        "utg1"
    )


def test_no_blind_is_null_and_a_posted_blind_is_never_none() -> None:
    assert mapping.blind(Blind.NONE) is None
    assert mapping.blind(Blind.SMALL) == "small"
    assert mapping.blind(Blind.BIG) == "big"
    assert mapping.participant(_participant(hole_cards=None, has_live_cards=True, blind=Blind.NONE)).blind is None
    assert mapping.posted_blind(Blind.SMALL) == "small"
    with pytest.raises(ValueError, match="Blind.NONE"):
        mapping.posted_blind(Blind.NONE)


@pytest.mark.parametrize(
    ("status", "expected"),
    [(None, None), (OccupantStatus.WAITING_TO_JOIN, "waiting_to_join"), (OccupantStatus.SITTING_OUT, "sitting_out")],
)
def test_a_ready_occupant_has_no_status(status: OccupantStatus | None, expected: str | None) -> None:
    seat = mapping.seat(
        SessionSeatView(number=3, display_name=DisplayName("Alice"), is_host=True),
        SeatView(number=3, occupant=OccupantView(stack=1000, status=status)),
    )
    assert seat.occupant is not None
    assert seat.occupant.status == expected
    assert (seat.occupant.display_name, seat.occupant.is_host, seat.occupant.stack) == ("Alice", True, 1000)


def test_an_empty_seat_has_no_occupant() -> None:
    seat = mapping.seat(SessionSeatView(number=4, display_name=None, is_host=False), SeatView(number=4, occupant=None))
    assert (seat.seat, seat.occupant) == (4, None)


def test_the_two_views_of_a_seat_must_agree_on_occupancy() -> None:
    with pytest.raises(AssertionError, match="occupancy"):
        mapping.seat(
            SessionSeatView(number=1, display_name=DisplayName("Alice"), is_host=True),
            SeatView(number=1, occupant=None),
        )


# --- Pots, showdowns and settlements (ADR 0009 §10) ---


def test_eligible_seats_are_ascending() -> None:
    assert mapping.pot(Pot(amount=30, eligible_seats=frozenset({5, 1, 3}))).eligible_seats == [1, 3, 5]


def test_eligible_seats_are_sorted_even_when_the_engines_set_iterates_out_of_order() -> None:
    """A `frozenset` of small integers usually iterates ascending by accident, so most examples cannot see the sort.

    `frozenset({8, 1})` iterates 8 then 1, which is the case that proves the wire order is really sorted
    (ADR 0009 §10), in a pot and in a settlement award alike. The shares keep the engine's odd-chip order.
    """
    unordered = frozenset({8, 1})
    assert list(unordered) != sorted(unordered), "this test needs a set that iterates out of order"

    assert mapping.ascending_seats(unordered) == [1, 8]
    assert mapping.pot(Pot(amount=30, eligible_seats=unordered)).eligible_seats == [1, 8]

    awarded = mapping.settlement(
        SettlementView(
            pot_awards=(PotAwardView(pot=Pot(amount=130, eligible_seats=unordered), shares=((8, 65), (1, 65))),),
            showdown_ranks=(),
        )
    )
    assert awarded.pot_awards[0].eligible_seats == [1, 8]
    assert [(share.seat, share.amount) for share in awarded.pot_awards[0].shares] == [(8, 65), (1, 65)]


def test_a_showdown_pairs_each_decision_with_its_seat_and_keeps_the_engines_order() -> None:
    record = Showdown(kind=ShowdownKind.INTERACTIVE, order=(2, 3, 1), decisions=(ShowdownAction.SHOW,))
    showdown = mapping.showdown(record)
    assert showdown.kind == "interactive"
    assert showdown.order == [2, 3, 1]
    assert [(entry.seat, entry.decision) for entry in showdown.decisions] == [(2, "show")]


def test_an_all_in_showdown_has_no_decisions() -> None:
    showdown = mapping.showdown(Showdown(kind=ShowdownKind.ALL_IN, order=(3, 1, 2)))
    assert (showdown.kind, showdown.order, showdown.decisions) == ("all_in", [3, 1, 2], [])


def _settlement(tiebreakers: Sequence[int]) -> SettlementView:
    return SettlementView(
        pot_awards=(PotAwardView(pot=Pot(amount=130, eligible_seats=frozenset({2, 1})), shares=((2, 66), (1, 64))),),
        showdown_ranks=((1, HandRank(HandCategory.TWO_PAIR, tuple(tiebreakers))),),
    )


def test_a_settlement_keeps_the_engines_pot_and_share_order_and_sorts_the_eligible_seats() -> None:
    settlement = mapping.settlement(_settlement((9, 7, 5)))
    award = settlement.pot_awards[0]
    assert (award.amount, award.eligible_seats) == (130, [1, 2])
    assert [(share.seat, share.amount) for share in award.shares] == [(2, 66), (1, 64)]


def test_a_shown_rank_carries_the_category_only_and_never_a_tiebreaker() -> None:
    settlement = mapping.settlement(_settlement((9, 7, 5)))
    assert [(rank.seat, rank.category) for rank in settlement.shown_ranks] == [(1, "two_pair")]
    serialized = settlement.model_dump(mode="json")
    assert serialized["shown_ranks"] == [{"seat": 1, "category": "two_pair"}]
    assert "tiebreakers" not in repr(serialized)


def test_a_strength_carries_the_category_the_description_and_the_five_cards() -> None:
    cards = (
        Card(Rank.KING, Suit.CLUBS),
        KING_OF_HEARTS,
        ACE_OF_HEARTS,
        Card(Rank.NINE, Suit.HEARTS),
        Card(Rank.SEVEN, Suit.DIAMONDS),
    )
    strength = mapping.strength(BestHand(HandRank(HandCategory.ONE_PAIR, (13, 14, 9, 7)), cards))
    assert strength.category == "one_pair"
    assert strength.description == "Pair of Kings"
    assert strength.cards == ["Kc", "Kh", "Ah", "9h", "7d"]
