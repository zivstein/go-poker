from dataclasses import dataclass
from itertools import pairwise

from go_poker.game.hand_state import HandPlayerState
from go_poker.game.poker_hand import PokerHand


@dataclass(frozen=True)
class Pot:
    """One pot layer: its chips and the live seats that can win it.

    The first pot of a hand is the main pot and any later ones are side pots. Who contributed to a layer is derived
    from the players' contributions when needed, so it is not stored here.
    """

    amount: int
    eligible_seats: frozenset[int]


def _collected_contribution(hand_player: HandPlayerState) -> int:
    """The chips the player has had collected into the middle: everything committed except the chips still in front."""
    return hand_player.total_contribution - hand_player.street_contribution


def middle_pot(hand: PokerHand) -> int:
    """The chips collected into the middle from completed betting rounds. Derived on request, never stored.

    It counts every player's collected contribution, folded players' included, and never the chips still in front of
    the players in the current round. Before settlement it is the physical, displayed pot and the boundary a future
    rake takes its share from. After settlement it is unchanged and describes what was contested; `hand.settlement`
    records that it was paid. It is not the pot-sizing base of a future Pot-Limit structure, which may need to count
    chips in front.
    """
    return sum(_collected_contribution(hand_player) for hand_player in hand.players)


def pots(hand: PokerHand) -> tuple[Pot, ...]:
    """The main pot and side pots, in order, derived from the players' collected contributions. Never stored.

    The layer boundaries (levels) are the distinct positive collected contributions of every participant, folded
    players included, in ascending order. Each level, with the previous level (0 for the first) below it, defines one
    pot: its amount is every participant's collected chips between the two levels, folded players' dead money
    included, and its eligible seats are the players who have not folded and whose collected contribution reaches the
    level. Adjacent pots may have the same eligible seats and are not merged. Chips still in front are not part of any
    pot, so before anything is collected there are none, and the pots always add up to the middle pot.
    """
    collected = [(hand_player, _collected_contribution(hand_player)) for hand_player in hand.players]
    levels = sorted({chips for _, chips in collected if chips > 0})
    return tuple(
        Pot(
            amount=sum(min(chips, level) - min(chips, previous) for _, chips in collected),
            eligible_seats=frozenset(
                hand_player.seat_number for hand_player, chips in collected if not hand_player.folded and chips >= level
            ),
        )
        for previous, level in pairwise((0, *levels))
    )
