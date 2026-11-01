from go_poker.game.betting.chips import return_chips
from go_poker.game.hand_state import HandPlayerState


def collect_round(players: tuple[HandPlayerState, ...]) -> tuple[int, int] | None:
    """Collect a completed betting round: return the unmatched chips, then move every player's chips in front into
    the middle.

    If exactly one participant has the highest total contribution, the chips above the highest total contribution of
    every other participant, folded players included, are uncalled and go back to that player's stack (see
    `return_chips`). Every street contribution, folded players' included, then resets to zero, so the remaining chips
    in front become part of the middle pot while the total contributions keep the normalized amounts.

    Earlier rounds were already collected this way, so the unmatched chips always come from the top player's chips in
    front. Run by the betting operation that completes the round, in the same call.

    Returns the returned excess as (seat number, chips), or None when nothing was returned. Collection records nothing:
    the calling operation records the return in the hand's history.
    """
    top_player = max(players, key=lambda hand_player: hand_player.total_contribution)
    matched = max(hand_player.total_contribution for hand_player in players if hand_player is not top_player)
    unmatched = top_player.total_contribution - matched
    returned = None
    if unmatched > 0:
        return_chips(top_player, unmatched)
        returned = (top_player.seat_number, unmatched)

    for hand_player in players:
        hand_player.street_contribution = 0
    return returned
