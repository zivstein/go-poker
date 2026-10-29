from go_poker.game.hand_state import HandPlayerState


class InvalidChipAmountError(ValueError):
    """Raised when committing a chip amount that is not positive."""


class InsufficientChipsError(ValueError):
    """Raised when committing more chips than the player has left in their stack."""


def commit_chips(hand_player: HandPlayerState, amount: int) -> None:
    """Move `amount` chips from the player's stack into their street and total contributions.

    The amount must be positive and no larger than the player's stack; otherwise nothing changes. A player whose stack
    reaches zero is marked all-in.
    """
    if amount <= 0:
        raise InvalidChipAmountError(f"Committed chips must be positive, got {amount}")
    if amount > hand_player.player.stack:
        raise InsufficientChipsError(
            f"Seat {hand_player.seat_number} has {hand_player.player.stack} chips but must commit {amount}"
        )

    hand_player.player.stack -= amount
    hand_player.street_contribution += amount
    hand_player.total_contribution += amount
    if hand_player.player.stack == 0:
        hand_player.all_in = True
