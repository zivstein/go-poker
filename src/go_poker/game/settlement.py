from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from go_poker.core.hand_rank import HandRank
from go_poker.game.betting.pots import Pot, pots
from go_poker.game.poker_hand import HandAlreadySettledError as HandAlreadySettledError
from go_poker.game.poker_hand import PokerHand, _require_unsettled


@dataclass(frozen=True)
class PotAward:
    """One pot and the chips each of its winning seats receives.

    `shares` are (seat, chips) pairs ordered clockwise starting with the first seat left of the button, the button
    last (heads-up, the big blind first). Odd chips can make the amounts unequal, and the larger ones come first.
    The winners are derived from the shares, never stored separately.
    """

    pot: Pot
    shares: tuple[tuple[int, int], ...]

    @property
    def winners(self) -> tuple[int, ...]:
        """The winning seats, in share order."""
        return tuple(seat for seat, _ in self.shares)


@dataclass(frozen=True)
class Settlement:
    """The immutable result of settling a hand: the award of every pot and each live player's showdown hand rank.

    `pot_awards` are in pot order. `showdown_ranks` are (seat, rank) pairs and are empty for an uncontested hand.
    Each seat's total payout is derived from the pot awards, never stored.
    """

    pot_awards: tuple[PotAward, ...]
    showdown_ranks: tuple[tuple[int, HandRank], ...]

    @property
    def payouts(self) -> dict[int, int]:
        """Each paid seat's total across all pot awards; unpaid seats are omitted. A fresh dict on every call."""
        totals: dict[int, int] = {}
        for pot_award in self.pot_awards:
            for seat, chips in pot_award.shares:
                totals[seat] = totals.get(seat, 0) + chips
        return totals


def _award_pot(pot: Pot, ranks: Mapping[int, HandRank], seat_order: Sequence[int]) -> PotAward:
    """Award one pot: to its only eligible seat, or split among the eligible seats holding the best rank."""
    contenders = [seat for seat in seat_order if seat in pot.eligible_seats]
    if len(pot.eligible_seats) == 1:
        winners = contenders
    else:
        best = max(ranks[seat] for seat in contenders)
        winners = [seat for seat in contenders if ranks[seat] == best]

    share, odd_chips = divmod(pot.amount, len(winners))
    return PotAward(
        pot=pot,
        shares=tuple((seat, share + (1 if index < odd_chips else 0)) for index, seat in enumerate(winners)),
    )


def _award_pots(
    pots: Sequence[Pot], ranks: Mapping[int, HandRank], seats_from_button: Sequence[int]
) -> tuple[PotAward, ...]:
    """Resolve each pot independently and return the awards in pot order. Internal; settle_hand is the public entry.

    A pot with one eligible seat goes wholly to that seat without consulting `ranks` (an uncontested hand passes none).
    Otherwise the eligible seats with the highest rank win it, equal ranks tie and suits never break a tie. Each tied
    winner gets amount // winners and the remainder chips go one each to the tied winners in odd-chip order: clockwise
    starting with the first seat left of the button, the button last. `shares` are in that same order.

    `seats_from_button` is the hand's seats clockwise with the button first, as in `hand.players`; this function does
    the rotation. It relies on engine invariants and does not validate: every eligible seat of a contested pot has a
    rank, `seats_from_button` contains every eligible seat, and the pots are engine-produced (each amount is at least
    its number of eligible seats, so every tied winner gets at least one chip).
    """
    seat_order = (*seats_from_button[1:], *seats_from_button[:1])
    return tuple(_award_pot(pot, ranks, seat_order) for pot in pots)


def _settle(hand: PokerHand, ranks: Mapping[int, HandRank]) -> None:
    """Settle the hand: award its pots, pay each winning seat and store the settlement. Internal; settle_hand is the
    public entry.

    This is shared engine implementation for variant entry points, not a client-facing API: callers must not supply
    arbitrary ranks. `ranks` holds every live seat's showdown rank, or is empty for an uncontested hand (see
    `_award_pots`). An already settled hand is rejected. The pots, the awards and the settlement are all derived before
    anything changes, so a rejection leaves the hand unchanged. Each winning seat's total payout is then added to its
    stack and its `all_in` is cleared, since the stack is positive again. Contributions, `folded` and the betting
    state are left as the hand's accounting history.

    It relies on engine invariants and does not validate them: the betting round is complete (nothing in front) and
    every live seat of a contested hand has a rank.
    """
    _require_unsettled(hand)
    pot_awards = _award_pots(pots(hand), ranks, [hand_player.seat_number for hand_player in hand.players])
    settlement = Settlement(pot_awards, tuple(ranks.items()))

    payouts = settlement.payouts
    for hand_player in hand.players:
        if hand_player.seat_number in payouts:
            hand_player.player.stack += payouts[hand_player.seat_number]
            hand_player.all_in = False
    hand.settlement = settlement
