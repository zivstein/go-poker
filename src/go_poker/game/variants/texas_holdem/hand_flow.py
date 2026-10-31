from go_poker.game.betting.actions import Action
from go_poker.game.betting.apply import apply_action
from go_poker.game.betting.initialization import _require_initializable, initialize_betting
from go_poker.game.betting.rounds import start_betting_round
from go_poker.game.betting.stakes import Stakes
from go_poker.game.poker_hand import PokerHand, _require_unsettled
from go_poker.game.showdown import ShowdownAction
from go_poker.game.street import Street
from go_poker.game.variants.texas_holdem.dealing import (
    _require_hole_cards_dealable,
    deal_hole_cards,
    deal_next_street,
)
from go_poker.game.variants.texas_holdem.showdown import (
    _live_count,
    _showdown_kind,
    apply_showdown_action,
    settle_hand,
    start_showdown,
)


def begin_hand(hand: PokerHand, stakes: Stakes) -> None:
    """Begin a Hold'em hand and advance it to its first decision: post the blinds, deal the hole cards, then run every
    step that needs no decision (see `act`).

    Checked in this order, each rejection leaving the hand unchanged:
    1. an already settled hand: `HandAlreadySettledError`;
    2. the checks of `initialize_betting`: `BettingAlreadyInitializedError`, then `BettingNotPreflopError`;
    3. the checks of `deal_hole_cards`: `HandPastPreflopError`, `HoleCardsAlreadyDealtError`, `DeckEmptyError`.
    All of them run before anything changes. Once they pass, execution begins: an unexpected engine defect raised
    later propagates, and there is no rollback.

    The hand ends settled (the blinds alone can end it), with a betting actor to act, or with a showdown decider to
    decide (see `current_actor`).
    """
    _require_unsettled(hand)
    _require_initializable(hand)
    _require_hole_cards_dealable(hand)
    initialize_betting(hand, stakes)
    deal_hole_cards(hand)
    _advance(hand)


def act(hand: PokerHand, seat: int, action: Action | ShowdownAction) -> None:
    """Apply a player's betting action or showdown decision, then advance the hand to its next decision.

    Checked in this order, each rejection leaving the hand unchanged and not advancing:
    1. an already settled hand: `HandAlreadySettledError`, whatever `action` is;
    2. `action` is neither an `Action` nor a `ShowdownAction`: `TypeError`, before any turn check;
    3. the errors of `apply_showdown_action` or `apply_action`, passed through unchanged, so a showdown action during
       betting raises `ShowdownNotStartedError` and a betting action during a showdown `NotPlayersTurnError`.
    Only after the action succeeds does the hand advance: the finished betting round is collected by the action, then
    the streets are dealt, betting rounds started, the showdown started and the hand settled as far as no decision is
    needed. Nobody but the players ever has to collect, deal, start a round or a showdown, or settle.

    The hand ends settled, with a betting actor to act, or with a showdown decider to decide (see `current_actor`). An
    unexpected engine defect raised while advancing propagates, and there is no rollback.
    """
    _require_unsettled(hand)
    if isinstance(action, ShowdownAction):
        apply_showdown_action(hand, seat, action)
    elif isinstance(action, Action):
        apply_action(hand, seat, action)
    else:
        raise TypeError(f"A betting Action or a ShowdownAction is expected, got {action!r}")
    _advance(hand)


def current_actor(hand: PokerHand) -> int | None:
    """The seat that must act next: the betting actor, or else the current showdown decider, or None when nobody must
    act. A settled hand and a hand that has not begun have no actor. A derived read, not guarded."""
    if hand.settlement is not None:
        return None
    if hand.betting is not None and hand.betting.current_actor is not None:
        return hand.betting.current_actor
    if hand.showdown is not None:
        return hand.showdown.current_decider
    return None


def _advance(hand: PokerHand) -> None:
    """Run every step that needs no player decision, until the hand is settled or a betting actor or showdown decider
    is waiting. Each step is derived from the hand, so no phase is stored.

    Every pass stops or makes progress (at most three streets dealt, one showdown started, one settlement), so it
    always ends.
    """
    while True:
        betting = hand.betting
        assert betting is not None  # only called once betting is initialized
        if hand.settlement is not None:
            return
        if _live_count(hand) == 1:
            settle_hand(hand)
            return
        if betting.current_actor is not None:
            return
        showdown = hand.showdown
        if showdown is not None:
            if not showdown.is_complete:
                return
            while hand.street is not Street.RIVER:
                deal_next_street(hand)
            settle_hand(hand)
            return
        if _showdown_kind(hand, betting) is not None:
            start_showdown(hand)
        else:
            deal_next_street(hand)
            start_betting_round(hand)
