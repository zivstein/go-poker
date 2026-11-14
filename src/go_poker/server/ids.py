"""The server's identifier and secret generators: table ids, join codes, credentials and user ids (ADR 0009 §2, §4).

Every generator here is the secure production default. `ServerConfig` holds them as seams so that a test can inject
fixed values, and it defaults to exactly these functions.
"""

import secrets
import uuid

from go_poker.app.identity import UserId

# ADR 0009 §2: six characters, with no 0/O/1/I/L to keep a spoken code unambiguous.
JOIN_CODE_ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
JOIN_CODE_LENGTH = 6
# 256 random bits, which `token_urlsafe` encodes as 43 base64url characters.
CREDENTIAL_BYTES = 32


def new_table_id() -> str:
    """A fresh lowercase UUID string, the permanent opaque address of one table."""
    return str(uuid.uuid4())


def new_join_code() -> str:
    """A fresh join code: `JOIN_CODE_LENGTH` characters drawn from `JOIN_CODE_ALPHABET` with `secrets`.

    Uniqueness among the active codes is the directory's responsibility, not this function's.
    """
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(JOIN_CODE_LENGTH))


def new_credential() -> str:
    """A fresh bearer credential for one membership of one table: `CREDENTIAL_BYTES` random bytes, base64url."""
    return secrets.token_urlsafe(CREDENTIAL_BYTES)


def new_user_id() -> UserId:
    """A fresh `UserId` for one membership. It never reaches the wire (ADR 0009 §2)."""
    return UserId(str(uuid.uuid4()))
