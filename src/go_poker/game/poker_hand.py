from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from go_poker.core.card import Card
from go_poker.core.deck import Deck
from go_poker.game.betting.state import BettingState
from go_poker.game.hand_history import HandHistory, HandParticipant, HandStarted
from go_poker.game.hand_state import HandPlayerState
from go_poker.game.showdown import Showdown
from go_poker.game.street import Street

if TYPE_CHECKING:
    # Type-only: settlement reaches PokerHand through the pots it derives from a hand.
    from go_poker.game.settlement import Settlement


class HandAlreadySettledError(RuntimeError):
    """Raised when a public hand operation is applied to a hand that is settled (carries its settlement)."""


class InvalidHandNumberError(ValueError):
    """Raised when a hand number is not a positive integer."""


def _require_valid_hand_number(number: int) -> None:
    """Reject anything but a positive integer (a bool is not one). The single source of the hand number rule."""
    if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
        raise InvalidHandNumberError("Hand number must be a positive integer")


def _hand_started(players: tuple[HandPlayerState, ...], number: int) -> HandStarted:
    return HandStarted(
        number=number,
        participants=tuple(
            HandParticipant(
                seat=hand_player.seat_number,
                player_id=hand_player.player.player_id,
                position=hand_player.position,
                blind=hand_player.blind,
                starting_stack=hand_player.player.stack,
            )
            for hand_player in players
        ),
    )


@dataclass(init=False)
class PokerHand:
    """One hand of poker: its participants, its own deck, the community board, the street and the burned cards.

    Participants come from hand setup, clockwise from the button; participation rules are not re-checked here.
    The deck is required: the hand owns the deck's state for the hand, but not its shuffle policy, which belongs to
    the lifecycle that creates the hand. A hand starts on the preflop street with an empty board and no burned cards;
    variant rules deal the board, burn cards and advance the street. The hand has no betting state until the betting
    layer initializes it; betting rules live in that layer, not here. It has no settlement until the hand is settled;
    the stored settlement is immutable, and its presence marks the hand as settled. It has no showdown until the
    showdown starts (see `Showdown`); the showdown record is started at most once, afterwards changes only by adding one
    decision at a time, is separate from the settlement, and is not cleared by settling.

    The hand is created as `PokerHand(players, deck, number)`; the number must be a positive integer. The hand owns its
    `history` (see `HandHistory`), which starts with `HandStarted` recorded at construction and is not a constructor
    argument. `number` reads the history. The other fields are not constructor arguments either.
    """

    players: tuple[HandPlayerState, ...]
    deck: Deck
    board: list[Card]
    street: Street
    # Cards burned before board cards; kept so every card drawn from the deck stays accounted for.
    burned_cards: list[Card]
    betting: BettingState | None
    settlement: Settlement | None
    showdown: Showdown | None
    history: HandHistory = field(init=False)

    def __init__(self, players: tuple[HandPlayerState, ...], deck: Deck, number: int) -> None:
        _require_valid_hand_number(number)
        started = _hand_started(players, number)
        self.players = players
        self.deck = deck
        self.board = []
        self.street = Street.PREFLOP
        self.burned_cards = []
        self.betting = None
        self.settlement = None
        self.showdown = None
        self.history = HandHistory((started,))

    @property
    def number(self) -> int:
        """The hand number, read from the history."""
        return self.history.number


def _require_unsettled(hand: PokerHand) -> None:
    """Reject a settled hand. Engine-internal; the first validation of every public hand-level mutation entry point."""
    if hand.settlement is not None:
        raise HandAlreadySettledError("This hand has already been settled")
