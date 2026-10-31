from go_poker.game.betting.actions import Action
from go_poker.game.betting.stakes import Stakes
from go_poker.game.game_lifecycle import (
    ButtonChooser,
    GameAlreadyStartedError,
    GameNotStartedError,
    start_game,
    start_next_hand,
)
from go_poker.game.poker_hand import PokerHand
from go_poker.game.showdown import ShowdownAction
from go_poker.game.table import Table
from go_poker.game.variants.texas_holdem import hand_flow


class HandInProgressError(RuntimeError):
    """Raised when the next hand is requested before the current hand is settled."""


class HoldemGame:
    """A continuous Hold'em game: one table and fixed stakes, played one hand after another.

    It only orchestrates the game lifecycle and `hand_flow`. It holds the table, the stakes and the current hand, and
    stores no phase, actor or "started" flag: `hand is None` is the only sign that the game has not started, and a hand
    is finished exactly when `hand.settlement is not None`. Button, participation, turn, legal-action and settlement
    rules stay in the layers below.

    Callers must not stand up a hand participant or directly change a participant's stack during a hand. This is not
    enforced. Mixing this level with low-level calls on `hand` is not supported.

    Every rejection leaves the table, the players, `hand` and the hand unchanged; `hand` is replaced only after both
    the lifecycle call and `begin_hand` succeed. Atomicity is narrow: an unexpected engine defect raised after the
    lifecycle returned propagates, and there is no rollback.
    """

    def __init__(self, table: Table, stakes: Stakes) -> None:
        self._table = table
        self._stakes = stakes
        self._hand: PokerHand | None = None

    @property
    def hand(self) -> PokerHand | None:
        """The current hand, or None before the game has started."""
        return self._hand

    def start(self, choose_button: ButtonChooser) -> PokerHand:
        """Start the game once and return its first hand, awaiting a decision or already settled.

        Checked in this order: a game that already has a hand, settled or not, raises `GameAlreadyStartedError`; then
        the errors of `start_game` pass through unchanged. `start` is never a restart.
        """
        if self._hand is not None:
            raise GameAlreadyStartedError("The game has already started")
        hand = start_game(self._table, choose_button)
        hand_flow.begin_hand(hand, self._stakes)
        self._hand = hand
        return hand

    def next_hand(self) -> PokerHand:
        """Move the button and return the next hand, awaiting a decision or already settled.

        Checked in this order: `GameNotStartedError` before `start`; `HandInProgressError` while the current hand is
        not settled; then the errors of `start_next_hand` pass through unchanged (for example `InvalidPlayerCount`
        when fewer than two players can play; there is no game-over state).
        """
        if self._hand is None:
            raise GameNotStartedError("The game has not started")
        if self._hand.settlement is None:
            raise HandInProgressError("The current hand is not settled")
        hand = start_next_hand(self._table)
        hand_flow.begin_hand(hand, self._stakes)
        self._hand = hand
        return hand

    def act(self, seat: int, action: Action | ShowdownAction) -> None:
        """Apply a betting action or showdown decision to the current hand; `hand_flow.act` rules apply unchanged.

        Before `start` this raises `GameNotStartedError`.
        """
        if self._hand is None:
            raise GameNotStartedError("The game has not started")
        hand_flow.act(self._hand, seat, action)
