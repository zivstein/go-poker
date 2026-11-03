"""`UserId` and `DisplayName` validation, equality and conflict key."""

import unicodedata

import pytest

from go_poker.app.identity import DisplayName, UserId


def test_user_id_is_an_opaque_non_empty_string_compared_by_value() -> None:
    assert UserId("u-1") == UserId("u-1")
    assert UserId("u-1") != UserId("u-2")
    assert UserId(" ").value == " "  # opaque: no trimming or other rule beyond non-empty


@pytest.mark.parametrize("bad", ["", None, 7, b"x"])
def test_user_id_rejects_anything_but_a_non_empty_string(bad: object) -> None:
    with pytest.raises(ValueError):
        UserId(bad)  # type: ignore[arg-type]


def test_display_name_is_nfc_normalized_and_trimmed_and_keeps_its_casing() -> None:
    name = DisplayName("  Café ")  # "e" + combining acute accent
    assert name.value == "Café"
    assert DisplayName("MiXeD").value == "MiXeD"


@pytest.mark.parametrize("length,valid", [(1, True), (20, True), (21, False)])
def test_display_name_length_is_one_to_twenty_after_normalization(length: int, valid: bool) -> None:
    if valid:
        assert len(DisplayName("x" * length).value) == length
    else:
        with pytest.raises(ValueError):
            DisplayName("x" * length)


@pytest.mark.parametrize("bad", ["", "   ", "\t\n", "a\tb", "a\x00b", "a​b", "a‮b", "a\x7fb"])
def test_display_name_rejects_empty_and_control_characters(bad: str) -> None:
    with pytest.raises(ValueError):
        DisplayName(bad)


def test_display_name_rejects_a_non_string() -> None:
    with pytest.raises(ValueError):
        DisplayName(5)  # type: ignore[arg-type]


def test_display_names_are_equal_by_their_normalized_value_only() -> None:
    assert DisplayName("Alice") == DisplayName("  Alice ")
    assert hash(DisplayName("Alice")) == hash(DisplayName(" Alice"))
    assert DisplayName("Café") == DisplayName("Café")  # NFC versus NFD
    assert DisplayName("Bob") != DisplayName("bob")
    assert DisplayName("Alice") != DisplayName("Alice2")
    assert DisplayName("Alice") != "Alice"


def test_conflict_key_ignores_case_and_normalization_where_equality_does_not() -> None:
    assert DisplayName("Bob") != DisplayName("bob")
    assert DisplayName("Bob").conflict_key == DisplayName("bob").conflict_key == "bob"
    assert DisplayName("Alice").conflict_key == DisplayName("  ALICE ").conflict_key
    assert DisplayName("Straße") != DisplayName("STRASSE")
    assert DisplayName("Straße").conflict_key == DisplayName("STRASSE").conflict_key
    assert DisplayName("Café") != DisplayName("CAFÉ")
    assert DisplayName("Café").conflict_key == DisplayName("CAFÉ").conflict_key
    assert DisplayName("Alice").conflict_key != DisplayName("Alice2").conflict_key


def test_conflict_key_is_nfc_normalized_after_casefold() -> None:
    name = DisplayName("İstanbul")  # casefold yields "i" + combining dot above
    assert name.conflict_key == unicodedata.normalize("NFC", name.conflict_key)
    assert name.conflict_key == DisplayName("i̇stanbul").conflict_key
