from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

from go_poker.core.hand_rank import HandRank
from go_poker.game.betting.pots import Pot, pots
from go_poker.game.poker_hand import HandAlreadySettledError as HandAlreadySettledError
from go_poker.game.poker_hand import PokerHand, _require_unsettled


@dataclass(frozen=True)
class PotAward:
    """One pot and the chips each of its winning seats receives.

    `pot` is the pot as derived and contested, so its eligible seats can include a seat that mucked and won nothing.

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
    """The immutable result of settling a hand: the award of every pot and each shown player's showdown hand rank.

    `pot_awards` are in pot order. `showdown_ranks` are (seat, rank) pairs of the shown seats only, in hand order, and
    are empty when nobody showed: an uncontested hand, or a contested one whose last contender won unshown. Each seat's
    total payout is derived from the pot awards, never stored.
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


class SettlementInvariantError(RuntimeError):
    """Raised when a pot violates a settlement invariant: an engine defect, never a reachable game state. There is no
    fallback payout."""


def _award_pot(
    pot: Pot, ranks: Mapping[int, HandRank], contenders: Collection[int], seat_order: Sequence[int]
) -> PotAward:
    """Award one pot among its final contenders: its eligible seats that are contenders, in odd-chip order. A sole final
    contender takes it whole without consulting `ranks`; otherwise the best rank wins and equal ranks split it."""
    final_contenders = [seat for seat in seat_order if seat in pot.eligible_seats and seat in contenders]
    if not final_contenders:
        raise SettlementInvariantError(f"A pot of {pot.amount} chips has no contender among its eligible seats")
    if len(final_contenders) == 1:
        winners = final_contenders
    else:
        unranked = [seat for seat in final_contenders if seat not in ranks]
        if unranked:
            raise SettlementInvariantError(f"A contested pot of {pot.amount} chips has contenders without a rank")
        best = max(ranks[seat] for seat in final_contenders)
        winners = [seat for seat in final_contenders if ranks[seat] == best]

    share, odd_chips = divmod(pot.amount, len(winners))
    return PotAward(
        pot=pot,
        shares=tuple((seat, share + (1 if index < odd_chips else 0)) for index, seat in enumerate(winners)),
    )


def _award_pots(
    pots: Sequence[Pot],
    ranks: Mapping[int, HandRank],
    contenders: Collection[int],
    seats_from_button: Sequence[int],
) -> tuple[PotAward, ...]:
    """Resolve each pot independently and return the awards in pot order. Internal; settle_hand is the public entry.

    `contenders` are the seats still competing at the end of the showdown. Each pot is awarded among its final
    contenders: its eligible seats that are contenders. The pot itself is not rewritten, so its eligible seats can
    include a seat that is not a contender and wins nothing. A pot with one final contender goes wholly to that seat
    without consulting `ranks`. Otherwise the final contenders with the highest rank win it, equal ranks tie and suits
    never break a tie. Each tied winner gets amount // winners and the remainder chips go one each to the tied winners
    in odd-chip order: clockwise starting with the first seat left of the button, the button last. `shares` are in that
    same order.

    Two invariants are checked for every pot, and a violation raises `SettlementInvariantError` with nothing changed
    (the awards are only derived here): every pot has at least one final contender, and a pot with more than one has a
    rank for each of them. Settlement never sees a showdown action, only these seats. `seats_from_button` is the
    hand's seats clockwise with the button first, as in `hand.players`; this function does the rotation. It relies on
    the remaining engine invariants and does not validate them: `seats_from_button` contains every eligible seat, and
    the pots are engine-produced (each amount is at least its number of eligible seats, so every tied winner gets at
    least one chip).
    """
    seat_order = (*seats_from_button[1:], *seats_from_button[:1])
    return tuple(_award_pot(pot, ranks, contenders, seat_order) for pot in pots)


def _settle(hand: PokerHand, ranks: Mapping[int, HandRank], contenders: Collection[int]) -> None:
    """Settle the hand: award its pots, pay each winning seat and store the settlement. Internal; settle_hand is the
    public entry.

    This is shared engine implementation for variant entry points, not a client-facing API: callers must not supply
    arbitrary ranks or contenders. `contenders` are the seats still competing for the pots (see `_award_pots`) and
    `ranks` holds the showdown rank of every shown seat, or is empty when nobody showed (an uncontested hand, or a
    last contender who won unshown). `ranks` is stored as the settlement's showdown ranks. An already settled hand is
    rejected. The pots, the awards and the settlement are all derived before anything changes, so a rejection,
    including a pot invariant violation, leaves the hand unchanged. Each winning seat's total payout is then added to
    its stack and its `all_in` is cleared, since the stack is positive again. Contributions, `folded` and the betting
    state are left as the hand's accounting history.

    It relies on engine invariants and does not validate the rest: the betting round is complete (nothing in front).
    """
    _require_unsettled(hand)
    pot_awards = _award_pots(pots(hand), ranks, contenders, [hand_player.seat_number for hand_player in hand.players])
    settlement = Settlement(pot_awards, tuple(ranks.items()))

    payouts = settlement.payouts
    for hand_player in hand.players:
        if hand_player.seat_number in payouts:
            hand_player.player.stack += payouts[hand_player.seat_number]
            hand_player.all_in = False
    hand.settlement = settlement
