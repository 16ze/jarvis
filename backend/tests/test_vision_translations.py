"""Tests du mapping OIV7 EN → FR."""
from vision_translations import translate_class, OIV7_FR_TRANSLATIONS


def test_translate_known_class_returns_french():
    assert translate_class("Mobile phone") == "téléphone"
    assert translate_class("Cat") == "chat"
    assert translate_class("Person") == "personne"


def test_translate_unknown_class_returns_lowercase_english():
    assert translate_class("UnknownThingy") == "unknownthingy"


def test_translate_handles_empty_string():
    assert translate_class("") == ""


def test_translations_dict_has_minimum_coverage():
    assert len(OIV7_FR_TRANSLATIONS) >= 30


def test_translations_keys_are_capitalized_english():
    for key in OIV7_FR_TRANSLATIONS.keys():
        assert key[0].isupper(), f"Clé non capitalisée: {key}"
