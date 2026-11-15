"""The in-memory table directory: every live table of this process, by id and by active join code (ADR 0008 §6).

It owns table creation, because that is where the identifiers are minted: the table id, the join code (unique among
the active codes), the host's `UserId` and the host's credential. Nothing here decides anything about poker or about
delivery; it hands a fresh `TableRuntime` the session it must drive.

A table leaves the directory when it fails, through the `on_failed` callback the runtime is built with, so a failed
table's id and code stop resolving and its credentials stop authenticating. There is no persistence: a restart loses
every table (ADR 0009 §13).
"""

from collections.abc import Callable
from dataclasses import dataclass

from go_poker.app.identity import DisplayName, UserId
from go_poker.app.session import TableSession
from go_poker.server.config import ServerConfig
from go_poker.server.runtime import TableRuntime

# A new code is drawn again when it collides with an active one. The bound turns an exhausted or broken generator
# into a loud failure instead of a hang.
JOIN_CODE_ATTEMPTS = 100


class JoinCodeUnavailableError(RuntimeError):
    """Raised when no free join code was found in `JOIN_CODE_ATTEMPTS` draws: a server defect or a full code space."""


def normalized_join_code(join_code: str) -> str:
    """The directory's key for a join code. Codes are matched case-insensitively (ADR 0009 §2), and the alphabet is
    uppercase, so the key is the uppercased text. A code outside the alphabet simply never matches."""
    return join_code.upper()


@dataclass(frozen=True)
class CreatedTable:
    """A table that has just been created, with its host's membership."""

    runtime: TableRuntime
    user_id: UserId
    credential: str
    seat: int


class TableDirectory:
    """Every live table of this process: `table_id` -> runtime, and active join code -> `table_id`."""

    def __init__(self, config: ServerConfig) -> None:
        self._config = config
        self._runtimes: dict[str, TableRuntime] = {}
        self._table_ids_by_code: dict[str, str] = {}

    def create(self, display_name: DisplayName) -> CreatedTable:
        """Create a table with `display_name` as its host, seated at the configured host seat with the buy-in.

        The identifiers come from the configured generators, the stakes, buy-in, seat count and host seat from the
        configuration, and the button chooser is handed to the session (ADR 0009 §4: these are server configuration,
        not protocol).
        """
        config = self._config
        table_id = config.new_table_id()
        join_code = self._free_join_code()
        user_id = config.new_user_id()
        credential = config.new_credential()
        session = TableSession.create(
            table_id,
            join_code,
            config.settings,
            user_id,
            display_name,
            config.host_seat,
            choose_button=config.choose_button,
        )
        runtime = TableRuntime(
            session,
            config,
            {credential: user_id},
            table_id=table_id,
            join_code=join_code,
            on_failed=self._forget(table_id, join_code),
        )
        self._runtimes[table_id] = runtime
        self._table_ids_by_code[normalized_join_code(join_code)] = table_id
        return CreatedTable(runtime=runtime, user_id=user_id, credential=credential, seat=config.host_seat)

    def get(self, table_id: str) -> TableRuntime | None:
        """The table with this id, or None when there is none. A failed table has already been forgotten."""
        return self._runtimes.get(table_id)

    def by_code(self, join_code: str) -> TableRuntime | None:
        """The open table with this join code, matched case-insensitively, or None.

        An unknown code, a malformed code and a failed table are all None here, so the caller cannot distinguish them
        (ADR 0009 §4).
        """
        table_id = self._table_ids_by_code.get(normalized_join_code(join_code))
        return None if table_id is None else self._runtimes.get(table_id)

    @property
    def table_ids(self) -> tuple[str, ...]:
        """The live tables' ids, in creation order."""
        return tuple(self._runtimes)

    def _free_join_code(self) -> str:
        for _ in range(JOIN_CODE_ATTEMPTS):
            join_code = self._config.new_join_code()
            if normalized_join_code(join_code) not in self._table_ids_by_code:
                return join_code
        raise JoinCodeUnavailableError(f"No free join code in {JOIN_CODE_ATTEMPTS} attempts")

    def _forget(self, table_id: str, join_code: str) -> Callable[[], None]:
        """What a table's runtime calls when it fails: drop the table and release its code."""

        def forget() -> None:
            self._runtimes.pop(table_id, None)
            code = normalized_join_code(join_code)
            if self._table_ids_by_code.get(code) == table_id:
                del self._table_ids_by_code[code]

        return forget
