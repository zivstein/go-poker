from go_poker.game.hand_state import HandPlayerState


def is_eligible(hand_player: HandPlayerState) -> bool:
    """An eligible player can still take a betting action: they have neither folded nor gone all-in."""
    return not hand_player.folded and not hand_player.all_in


def pending_at_round_start(players: tuple[HandPlayerState, ...], current_bet: int) -> set[int]:
    """Return the seat numbers that owe an action when a betting round starts.

    Every eligible player is pending. When at most one player is eligible, no opponent can respond, so only an eligible
    player who still owes chips to the current bet is pending; otherwise the round is complete as soon as it starts.
    """
    eligible = [hand_player for hand_player in players if is_eligible(hand_player)]
    if len(eligible) <= 1:
        return {hand_player.seat_number for hand_player in eligible if hand_player.street_contribution < current_bet}
    return {hand_player.seat_number for hand_player in eligible}


def first_pending_after(players: tuple[HandPlayerState, ...], anchor_seat_number: int, pending: set[int]) -> int | None:
    """Return the first pending seat clockwise after the anchor seat, or None when nobody is pending.

    `players` is ordered clockwise from the button, so the search follows that order and wraps around it.
    """
    seats = [hand_player.seat_number for hand_player in players]
    anchor_index = seats.index(anchor_seat_number)
    clockwise_after_anchor = seats[anchor_index + 1 :] + seats[: anchor_index + 1]
    return next((seat_number for seat_number in clockwise_after_anchor if seat_number in pending), None)
