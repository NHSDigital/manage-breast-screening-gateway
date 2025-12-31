from unittest.mock import MagicMock

from pynetdicom.events import Event

from services.dicom import SUCCESS
from services.dicom.c_echo import CEcho


class TestCEcho:
    def test_call(self):
        event = MagicMock(spec=Event)
        assert CEcho().call(event) == SUCCESS
