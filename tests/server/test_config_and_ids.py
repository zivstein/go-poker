"""`ServerConfig` and the identifier generators (C6.4 Brief §2.7, §2.10; ADR 0009 §2).

The point of these tests is that every default is the production behavior, the seams included, and that overriding a
seam really replaces it.
"""

import secrets
import uuid

from go_poker.app.identity import UserId
from go_poker.game.betting.stakes import Stakes
from go_poker.server import ids, timers
from go_poker.server.config import ServerConfig


def test_the_table_defaults_are_the_contracts_fixture_values() -> None:
    config = ServerConfig()
    assert (config.small_blind, config.big_blind, config.buy_in, config.max_seats, config.host_seat) == (
        5,
        10,
        1000,
        6,
        1,
    )
    assert config.stakes == Stakes(small_blind=5, big_blind=10)
    assert (config.settings.stakes, config.settings.buy_in, config.settings.max_seats) == (config.stakes, 1000, 6)


def test_the_timings_and_limits_are_the_briefs_values() -> None:
    config = ServerConfig()
    assert (config.next_hand_pause_seconds, config.hello_timeout_seconds) == (5.0, 10.0)
    assert (config.outbox_size, config.max_inbound_frame_bytes) == (256, 16 * 1024)


def test_every_seam_defaults_to_the_secure_generator() -> None:
    config = ServerConfig()
    assert config.new_table_id is ids.new_table_id
    assert config.new_join_code is ids.new_join_code
    assert config.new_credential is ids.new_credential
    assert config.new_user_id is ids.new_user_id
    assert config.choose_button is secrets.choice
    assert config.new_next_hand_scheduler is timers.AsyncioNextHandScheduler
    assert isinstance(config.new_next_hand_scheduler(), timers.AsyncioNextHandScheduler)


def test_a_seam_can_be_replaced_without_touching_the_others() -> None:
    config = ServerConfig(new_table_id=lambda: "table-1", choose_button=min)
    assert config.new_table_id() == "table-1"
    assert config.choose_button((3, 1, 2)) == 1
    assert config.new_join_code is ids.new_join_code


def test_a_table_id_is_a_fresh_lowercase_uuid() -> None:
    first, second = ids.new_table_id(), ids.new_table_id()
    assert first != second
    assert first == first.lower()
    assert str(uuid.UUID(first)) == first


def test_a_join_code_is_six_characters_of_the_contracts_alphabet() -> None:
    assert ids.JOIN_CODE_ALPHABET == "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
    assert set("01IOL").isdisjoint(ids.JOIN_CODE_ALPHABET)
    codes = {ids.new_join_code() for _ in range(50)}
    assert all(len(code) == 6 and set(code) <= set(ids.JOIN_CODE_ALPHABET) for code in codes)
    assert len(codes) > 1, "the generator must not be constant"


def test_a_credential_is_a_base64url_secret_of_256_bits() -> None:
    credential = ids.new_credential()
    assert credential != ids.new_credential()
    assert len(credential) == 43
    assert set(credential) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


def test_a_user_id_is_a_fresh_uuid_and_never_the_credential() -> None:
    user_id = ids.new_user_id()
    assert isinstance(user_id, UserId)
    assert str(uuid.UUID(user_id.value)) == user_id.value
    assert user_id != ids.new_user_id()
