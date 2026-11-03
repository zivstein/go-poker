"""The identity facts a table needs: the opaque `UserId` and the table-visible `DisplayName`.

The caller supplies both. Accounts, usernames, authentication, minting ids and mapping credentials to a `UserId` live
outside this layer.
"""

import unicodedata
from dataclasses import dataclass

DISPLAY_NAME_MAX_LENGTH = 20


@dataclass(frozen=True)
class UserId:
    """The one logical identity of a user: an opaque, non-empty string.

    The engine receives it as `Player.player_id`, so the engine's `player_id` and the application's `UserId` are the
    same identity at two boundaries. It never appears in a view.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or self.value == "":
            raise ValueError("A user id must be a non-empty string")


@dataclass(frozen=True)
class DisplayName:
    """The display name a table shows for a member, supplied by the caller; table display policy only.

    It is NFC-normalized and trimmed, 1-20 characters, with no character of Unicode general category C (control, format
    such as zero-width and bidi-override characters, surrogate, private-use, unassigned). `value` keeps the caller's own
    casing, and two display names are equal when their normalized values are equal. `conflict_key` is what a table
    compares to keep the names of its current members distinct. Invalid input raises `ValueError` at construction.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise ValueError("A display name must be a string")
        normalized = unicodedata.normalize("NFC", self.value).strip()
        if not 1 <= len(normalized) <= DISPLAY_NAME_MAX_LENGTH:
            raise ValueError(f"A display name must have 1-{DISPLAY_NAME_MAX_LENGTH} characters")
        if any(unicodedata.category(character).startswith("C") for character in normalized):
            raise ValueError(
                "A display name cannot contain control, format, surrogate, private-use or unassigned characters"
            )
        object.__setattr__(self, "value", normalized)

    @property
    def conflict_key(self) -> str:
        """The NFC normalization of the casefolded value (casefold can leave the text denormalized)."""
        return unicodedata.normalize("NFC", self.value.casefold())
