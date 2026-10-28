"""Shared DICOM character set handling."""

from pydicom.dataset import Dataset

from services import dicom


class CharacterSet:
    """Helper for resolving and applying DICOM SpecificCharacterSet values."""

    @classmethod
    def resolve(cls, dataset: Dataset | None = None) -> str:
        """Resolve character set from a Dataset (e.g. request attribute list/identifier)."""
        try:
            if dataset is None:
                return dicom.CHARSET_DEFAULT

            specific_char_set = dataset.get("SpecificCharacterSet")
            if specific_char_set is None:
                return dicom.CHARSET_DEFAULT

            if isinstance(specific_char_set, (list, tuple)) and len(specific_char_set) > 0:
                charset = specific_char_set[0]
            else:
                charset = specific_char_set

            if isinstance(charset, str):
                charset = charset.strip()
            else:
                return dicom.CHARSET_DEFAULT

            if charset in dicom.ALLOWED_CHARSETS:
                return charset

            if charset in ("ISO-IR 192", "UTF-8", "utf-8"):
                return dicom.CHARSET_UTF8
            if charset in ("ISO-IR 100", "ISO_IR100"):
                return dicom.CHARSET_ISO_IR_100
            if charset in ("ISO-IR 6", "ISO_IR6", "ASCII"):
                return dicom.CHARSET_ISO_IR_6

            return dicom.CHARSET_DEFAULT
        except Exception:
            return dicom.CHARSET_DEFAULT

    @staticmethod
    def get_default() -> str:
        return dicom.CHARSET_DEFAULT

    @staticmethod
    def get_allowed_charsets() -> set[str]:
        return set(dicom.ALLOWED_CHARSETS)
