import pytest

from go_poker.game.betting.no_limit import has_raise_rights
from go_poker.game.betting.stakes import Stakes
from go_poker.game.betting.state import BettingState
from go_poker.game.street import Street

# The reopening rule is checked at its boundaries on betting states built directly; the legal-actions and integration
# tests reach such states through real short all-in action sequences.


def flop_betting(*, current_bet: int, last_full_raise_size: int, acted_at_bet: dict[int, int]) -> BettingState:
    """A flop betting state at blinds 50/100 with seat 1 to act and nobody else pending."""
    return BettingState(
        street=Street.FLOP,
        stakes=Stakes(small_blind=50, big_blind=100),
        current_bet=current_bet,
        last_full_raise_size=last_full_raise_size,
        current_actor=1,
        pending_actors={1},
        acted_at_bet=acted_at_bet,
        last_aggressor=None,
    )


def test_player_who_has_not_acted_has_raise_rights() -> None:
    """Seat 2 opened with a short all-in bet of 30, below the full bet of 100. Seat 1 has not acted this round, so it
    may still raise, however small the bet it faces."""
    betting = flop_betting(current_bet=30, last_full_raise_size=100, acted_at_bet={2: 30})
    assert has_raise_rights(betting, 1)


@pytest.mark.parametrize(
    "acted_at, current_bet, last_full_raise_size, expected",
    [
        # Seat 1 bet 50 and seat 2 went all-in to 70: 20 more is below the full raise of 50.
        pytest.param(50, 70, 50, False, id="increase-below-a-full-raise"),
        # Seat 1 bet 100, then short all-ins to 160 and 200: together they add exactly one full raise of 100.
        pytest.param(100, 200, 100, True, id="cumulative-increase-of-exactly-a-full-raise"),
        # Seat 1 checked at 0 and faces a full bet of 100 raised to 250.
        pytest.param(0, 250, 150, True, id="increase-above-a-full-raise"),
    ],
)
def test_player_who_acted_has_raise_rights_only_after_a_full_raise_since(
    acted_at: int, current_bet: int, last_full_raise_size: int, expected: bool
) -> None:
    """A player who acted may raise again only once the current bet has risen by at least the last full raise size
    since their latest action, however many bets or raises that increase took."""
    betting = flop_betting(
        current_bet=current_bet, last_full_raise_size=last_full_raise_size, acted_at_bet={1: acted_at}
    )
    assert has_raise_rights(betting, 1) is expected
