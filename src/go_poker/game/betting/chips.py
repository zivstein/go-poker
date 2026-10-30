from go_poker.game.hand_state import HandPlayerState


class InvalidChipAmountError(ValueError):
    """Raised when committing or returning a chip amount that is not positive."""


class InsufficientChipsError(ValueError):
    """Raised when committing more chips than the player has left in their stack."""


class InsufficientChipsInFrontError(ValueError):
    """Raised when returning more chips than the player has in front of them (their street contribution)."""


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


def return_chips(hand_player: HandPlayerState, amount: int) -> None:
    """Move `amount` chips from in front of the player back to their stack, lowering both contributions.

    Only uncollected chips in front can be returned: the amount must be positive and no larger than the player's
    street contribution; otherwise nothing changes. The player's stack is positive again, so they are no longer
    all-in.
    """
    if amount <= 0:
        raise InvalidChipAmountError(f"Returned chips must be positive, got {amount}")
    if amount > hand_player.street_contribution:
        raise InsufficientChipsInFrontError(
            f"Seat {hand_player.seat_number} has {hand_player.street_contribution} chips in front but must get "
            f"{amount} back"
        )

    hand_player.player.stack += amount
    hand_player.street_contribution -= amount
    hand_player.total_contribution -= amount
    hand_player.all_in = False
