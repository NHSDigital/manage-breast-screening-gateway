"""Tests for character set handling."""

from pydicom import Dataset

from services.dicom import (
    ALLOWED_CHARSETS,
    CHARSET_DEFAULT,
    CHARSET_ISO_IR_6,
    CHARSET_ISO_IR_100,
    CHARSET_UTF8,
)
from services.dicom.character_set import CharacterSet


class TestCharacterSet:
    """Tests for CharacterSet."""

    def test_default_when_dataset_is_none(self):
        """Default is used when dataset is None."""
        assert CharacterSet.resolve(None) == CHARSET_DEFAULT

    def test_default_when_specific_character_set_missing(self):
        """Default is used when SpecificCharacterSet is not present."""
        ds = Dataset()
        assert CharacterSet.resolve(ds) == CHARSET_DEFAULT

    def test_supports_iso_ir_192_utf8(self):
        """ISO_IR 192 (UTF-8) is supported."""
        ds = Dataset()
        ds.SpecificCharacterSet = CHARSET_UTF8
        assert CharacterSet.resolve(ds) == CHARSET_UTF8

    def test_supports_iso_ir_100(self):
        """ISO_IR 100 is supported."""
        ds = Dataset()
        ds.SpecificCharacterSet = CHARSET_ISO_IR_100
        assert CharacterSet.resolve(ds) == CHARSET_ISO_IR_100

    def test_supports_iso_ir_6(self):
        """ISO_IR 6 is supported."""
        ds = Dataset()
        ds.SpecificCharacterSet = CHARSET_ISO_IR_6
        assert CharacterSet.resolve(ds) == CHARSET_ISO_IR_6

    def test_handles_list_form(self):
        """Handles SpecificCharacterSet as a list."""
        ds = Dataset()
        ds.SpecificCharacterSet = [CHARSET_ISO_IR_100]
        assert CharacterSet.resolve(ds) == CHARSET_ISO_IR_100

        ds = Dataset()
        ds.SpecificCharacterSet = [CHARSET_ISO_IR_6]
        assert CharacterSet.resolve(ds) == CHARSET_ISO_IR_6

        ds = Dataset()
        ds.SpecificCharacterSet = [CHARSET_UTF8]
        assert CharacterSet.resolve(ds) == CHARSET_UTF8

    def test_handles_tuple_form(self):
        """Handles SpecificCharacterSet as a tuple."""
        ds = Dataset()
        ds.SpecificCharacterSet = (CHARSET_ISO_IR_100,)
        assert CharacterSet.resolve(ds) == CHARSET_ISO_IR_100

    def test_normalises_common_variants(self):
        """Normalises common variants to supported values."""
        ds = Dataset()
        ds.SpecificCharacterSet = "ISO-IR 192"
        assert CharacterSet.resolve(ds) == CHARSET_UTF8

        ds = Dataset()
        ds.SpecificCharacterSet = "UTF-8"
        assert CharacterSet.resolve(ds) == CHARSET_UTF8

        ds = Dataset()
        ds.SpecificCharacterSet = "utf-8"
        assert CharacterSet.resolve(ds) == CHARSET_UTF8

        ds = Dataset()
        ds.SpecificCharacterSet = "ISO-IR 100"
        assert CharacterSet.resolve(ds) == CHARSET_ISO_IR_100

        ds = Dataset()
        ds.SpecificCharacterSet = "ISO_IR100"
        assert CharacterSet.resolve(ds) == CHARSET_ISO_IR_100

        ds = Dataset()
        ds.SpecificCharacterSet = "ISO-IR 6"
        assert CharacterSet.resolve(ds) == CHARSET_ISO_IR_6

        ds = Dataset()
        ds.SpecificCharacterSet = "ISO_IR6"
        assert CharacterSet.resolve(ds) == CHARSET_ISO_IR_6

        ds = Dataset()
        ds.SpecificCharacterSet = "ASCII"
        assert CharacterSet.resolve(ds) == CHARSET_ISO_IR_6

    def test_defaults_on_unknown_charset(self):
        """Defaults to default charset on unknown values."""
        ds = Dataset()
        ds.SpecificCharacterSet = "ISO_IR 127"
        assert CharacterSet.resolve(ds) == CHARSET_DEFAULT

        ds = Dataset()
        ds.SpecificCharacterSet = ["GB18030"]
        assert CharacterSet.resolve(ds) == CHARSET_DEFAULT

    def test_strips_whitespace(self):
        """Strips whitespace from charset values."""
        ds = Dataset()
        ds.SpecificCharacterSet = "  ISO_IR 100  "
        assert CharacterSet.resolve(ds) == CHARSET_ISO_IR_100

    def test_allowed_charsets_and_default_exported(self):
        """Allowed charsets and defaults are accessible."""
        allowed = CharacterSet.get_allowed_charsets()
        assert CHARSET_UTF8 in allowed
        assert CHARSET_ISO_IR_100 in allowed
        assert CHARSET_ISO_IR_6 in allowed
        assert ALLOWED_CHARSETS == allowed
        assert CharacterSet.get_default() == CHARSET_DEFAULT
        assert CHARSET_DEFAULT == CHARSET_UTF8
