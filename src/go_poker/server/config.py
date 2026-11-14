"""`ServerConfig`: the server's configuration, one frozen value (C6.4 Brief §2.10).

Every field has a default that is the production behavior, including the test-only seams: the identifier generators
and the button chooser default to `secrets`-backed functions, so a server built with `ServerConfig()` is the secure
one. A test replaces only what it needs to make a scenario reproducible.

Stakes, buy-in, seat count and the host's seat are server configuration, not protocol (ADR 0009 §4).
"""

import secrets
from collections.abc import Callable
from dataclasses import dataclass

from go_poker.app.identity import UserId
from go_poker.app.views import TableSettings
from go_poker.game.betting.stakes import Stakes
from go_poker.game.game_lifecycle import ButtonChooser
from go_poker.server import ids, timers
from go_poker.server.timers import NextHandScheduler


@dataclass(frozen=True)
class ServerConfig:
    """How this server builds and runs its tables.

    - the table defaults: the blinds, the buy-in every member sits with, the seat count and the host's seat;
    - the timings: the next-hand pause and the hello timeout, both in seconds;
    - the limits: the per-connection outbox size and the largest inbound text frame, in UTF-8 bytes;
    - the seams: the table id, join code, credential and user id generators, the button chooser, and the next-hand
      scheduler.

    Ping and pong are transport settings of the dev command, not configuration (ADR 0009 §5).
    """

    small_blind: int = 5
    big_blind: int = 10
    buy_in: int = 1000
    max_seats: int = 6
    host_seat: int = 1
    next_hand_pause_seconds: float = 5.0
    hello_timeout_seconds: float = 10.0
    outbox_size: int = 256
    max_inbound_frame_bytes: int = 16384
    new_table_id: Callable[[], str] = ids.new_table_id
    new_join_code: Callable[[], str] = ids.new_join_code
    new_credential: Callable[[], str] = ids.new_credential
    new_user_id: Callable[[], UserId] = ids.new_user_id
    choose_button: ButtonChooser = secrets.choice
    new_next_hand_scheduler: Callable[[], NextHandScheduler] = timers.AsyncioNextHandScheduler

    @property
    def stakes(self) -> Stakes:
        """The blinds a new table plays; `Stakes` validates them."""
        return Stakes(small_blind=self.small_blind, big_blind=self.big_blind)

    @property
    def settings(self) -> TableSettings:
        """The `TableSettings` a new `TableSession` is created with; the application layer validates them."""
        return TableSettings(stakes=self.stakes, buy_in=self.buy_in, max_seats=self.max_seats)
