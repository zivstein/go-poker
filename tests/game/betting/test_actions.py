import pytest

from go_poker.game.betting.actions import Action, ActionType, InvalidActionError


@pytest.mark.parametrize(
    "action_type, amount",
    [
        pytest.param(ActionType.FOLD, None, id="fold"),
        pytest.param(ActionType.CHECK, None, id="check"),
        pytest.param(ActionType.CALL, None, id="call"),
        pytest.param(ActionType.BET, 1, id="bet"),
        pytest.param(ActionType.RAISE, 500, id="raise"),
    ],
)
def test_well_formed_actions_keep_their_target(action_type: ActionType, amount: int | None) -> None:
    """Bet and raise carry a positive target amount; fold, check and call carry none."""
    action = Action(action_type, amount)
    assert (action.type, action.amount) == (action_type, amount)


@pytest.mark.parametrize(
    "action_type, amount",
    [
        pytest.param(ActionType.BET, None, id="bet-without-amount"),
        pytest.param(ActionType.BET, 0, id="bet-to-zero"),
        pytest.param(ActionType.RAISE, -5, id="raise-to-negative"),
        pytest.param(ActionType.FOLD, 10, id="fold-with-amount"),
        pytest.param(ActionType.CHECK, 10, id="check-with-amount"),
        pytest.param(ActionType.CALL, 10, id="call-with-amount"),
    ],
)
def test_malformed_actions_are_rejected(action_type: ActionType, amount: int | None) -> None:
    """Bet and raise need a positive target amount, and fold, check and call may not carry one."""
    with pytest.raises(InvalidActionError):
        Action(action_type, amount)
