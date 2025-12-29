import os
from unittest.mock import patch

from pynetdicom import evt

from services.dicom.server import PACSServer, main

tmp_dir = f"{os.path.dirname(os.path.realpath(__file__))}/tmp"


@patch(f"{PACSServer.__module__}.PACSStorage")
class TestServer:
    def test_init(self, mock_storage):
        subject = PACSServer("Custom AE Title", 2222, tmp_dir, f"{tmp_dir}/test.db")

        assert subject.ae_title == "Custom AE Title"
        assert subject.port == 2222
        assert subject.storage == mock_storage.return_value
        assert subject.ae is None

        mock_storage.assert_called_once_with(f"{tmp_dir}/test.db", tmp_dir)

    def test_init_defaults(self, mock_storage):
        subject = PACSServer()

        assert subject.ae_title == "SCREENING_PACS"
        assert subject.port == 4244
        assert subject.storage == mock_storage.return_value
        assert subject.ae is None

        mock_storage.assert_called_once_with("/var/lib/pacs/pacs.db", "/var/lib/pacs/storage")

    @patch(f"{PACSServer.__module__}.AE")
    @patch(f"{PACSServer.__module__}.CStore")
    def test_start(self, mock_c_store, mock_ae, mock_storage):
        subject = PACSServer()
        subject.start()

        assert subject.ae == mock_ae.return_value

        mock_ae.assert_called_once_with(ae_title="SCREENING_PACS")
        mock_ae.return_value.start_server.assert_called_once_with(
            ("0.0.0.0", 4244), evt_handlers=[(evt.EVT_C_STORE, mock_c_store.return_value.call)]
        )

    @patch(f"{PACSServer.__module__}.AE")
    def test_stop(self, mock_ae, mock_storage):
        subject = PACSServer()
        subject.start()
        subject.stop()

        subject.ae.shutdown.assert_called_once()
        subject.storage.close.assert_called_once()


def test_main(monkeypatch):
    monkeypatch.setenv("PACS_AET", "Custom AE Title")
    monkeypatch.setenv("PACS_PORT", "2222")
    monkeypatch.setenv("PACS_STORAGE_PATH", "/some/path")
    monkeypatch.setenv("PACS_DB_PATH", "/some/path/test.db")

    with patch(f"{PACSServer.__module__}.PACSServer") as mock_server:
        main()

        mock_server.assert_called_once_with("Custom AE Title", 2222, "/some/path", "/some/path/test.db")


def test_main_using_defaults():
    with patch(f"{PACSServer.__module__}.PACSServer") as mock_server:
        main()

        mock_server.assert_called_once_with("SCREENING_PACS", 4244, "/var/lib/pacs/storage", "/var/lib/pacs/pacs.db")


def test_main_keyboard_interrupt():
    with patch(f"{PACSServer.__module__}.PACSServer") as mock_server:
        mock_server.return_value.start.side_effect = KeyboardInterrupt()

        main()

        mock_server.return_value.stop.assert_called_once()
