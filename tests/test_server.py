from typing import cast
from unittest.mock import MagicMock, Mock, patch

from pynetdicom import evt

from server import MWLServer, PACSServer, main


@patch(f"{PACSServer.__module__}.PACSStorage")
class TestPACSServer:
    def test_init(self, mock_storage, tmp_dir):
        subject = PACSServer("Custom AE Title", 2222, tmp_dir, f"{tmp_dir}/test.db", False)

        assert subject.ae_title == "Custom AE Title"
        assert subject.port == 2222
        assert subject.storage == mock_storage.return_value
        assert subject.ae is None
        assert subject.block is False

        mock_storage.assert_called_once_with(f"{tmp_dir}/test.db", tmp_dir)

    def test_init_defaults(self, mock_storage):
        subject = PACSServer()

        assert subject.ae_title == "SCREENING_PACS"
        assert subject.port == 4244
        assert subject.storage == mock_storage.return_value
        assert subject.ae is None
        assert subject.block is True

        mock_storage.assert_called_once_with("/var/lib/pacs/pacs.db", "/var/lib/pacs/storage")

    @patch(f"{PACSServer.__module__}.AE")
    @patch(f"{PACSServer.__module__}.CEcho")
    @patch(f"{PACSServer.__module__}.CStore")
    def test_start(self, mock_c_store, mock_c_echo, mock_ae, _):
        subject = PACSServer()
        subject.start()

        assert subject.ae == mock_ae.return_value

        mock_ae.assert_called_once_with(ae_title="SCREENING_PACS")
        mock_ae.return_value.start_server.assert_called_once_with(
            ("0.0.0.0", 4244),
            block=True,
            evt_handlers=[
                (evt.EVT_C_ECHO, mock_c_echo.return_value.call),
                (evt.EVT_C_STORE, mock_c_store.return_value.call),
            ],
        )

    @patch(f"{PACSServer.__module__}.AE")
    def test_stop(self, *_):
        subject = PACSServer()
        subject.start()
        subject.stop()

        cast(Mock, subject.ae).shutdown.assert_called_once()
        cast(Mock, subject.storage).close.assert_called_once()


@patch(f"{MWLServer.__module__}.WorklistStorage")
class TestMWLServer:
    def test_init(self, mock_storage):
        subject = MWLServer("CUSTOM_MWL", 11112, "/custom/path/worklist.db", False)

        assert subject.ae_title == "CUSTOM_MWL"
        assert subject.port == 11112
        assert subject.storage == mock_storage.return_value
        assert subject.ae is None
        assert subject.block is False

        mock_storage.assert_called_once_with("/custom/path/worklist.db")

    def test_init_defaults(self, mock_storage):
        subject = MWLServer()

        assert subject.ae_title == "MWL_SCP"
        assert subject.port == 4243
        assert subject.storage == mock_storage.return_value
        assert subject.ae is None
        assert subject.block is True

        mock_storage.assert_called_once_with("/var/lib/pacs/worklist.db")

    @patch(f"{MWLServer.__module__}.AE")
    def test_start(self, mock_ae, _):
        subject = MWLServer()
        mock_ae_instance = MagicMock()
        mock_ae.return_value = mock_ae_instance

        subject.start()

        assert subject.ae == mock_ae_instance

        mock_ae.assert_called_once_with(ae_title="MWL_SCP")
        mock_ae_instance.add_supported_context.assert_called_once()
        mock_ae_instance.start_server.assert_called_once()
        args, kwargs = mock_ae_instance.start_server.call_args
        assert args[0] == ("0.0.0.0", 4243)
        assert kwargs["block"] is True
        assert "evt_handlers" in kwargs
        assert len(kwargs["evt_handlers"]) == 1

    @patch(f"{MWLServer.__module__}.AE")
    def test_stop(self, *_):
        subject = MWLServer()
        subject.start()
        subject.stop()

        cast(Mock, subject.ae).shutdown.assert_called_once()


def test_main(monkeypatch):
    monkeypatch.setenv("PACS_AET", "Custom AE Title")
    monkeypatch.setenv("PACS_PORT", "2222")
    monkeypatch.setenv("PACS_STORAGE_PATH", "/some/path")
    monkeypatch.setenv("PACS_DB_PATH", "/some/path/test.db")
    monkeypatch.setenv("MWL_AET", "Custom MWL")
    monkeypatch.setenv("MWL_PORT", "3333")
    monkeypatch.setenv("MWL_DB_PATH", "/some/path/worklist.db")

    with (
        patch(f"{PACSServer.__module__}.PACSServer") as mock_pacs,
        patch(f"{MWLServer.__module__}.MWLServer") as mock_mwl,
        patch(f"{PACSServer.__module__}.threading.Thread"),
    ):
        main()

        mock_pacs.assert_called_once_with("Custom AE Title", 2222, "/some/path", "/some/path/test.db", block=True)
        mock_mwl.assert_called_once_with("Custom MWL", 3333, "/some/path/worklist.db", block=True)


def test_main_using_defaults():
    with (
        patch(f"{PACSServer.__module__}.PACSServer") as mock_pacs,
        patch(f"{MWLServer.__module__}.MWLServer") as mock_mwl,
        patch(f"{PACSServer.__module__}.threading.Thread"),
    ):
        main()

        mock_pacs.assert_called_once_with(
            "SCREENING_PACS", 4244, "/var/lib/pacs/storage", "/var/lib/pacs/pacs.db", block=True
        )
        mock_mwl.assert_called_once_with("MWL_SCP", 4243, "/var/lib/pacs/worklist.db", block=True)


def test_main_keyboard_interrupt():
    with (
        patch(f"{PACSServer.__module__}.PACSServer") as mock_pacs,
        patch(f"{MWLServer.__module__}.MWLServer") as mock_mwl,
        patch(f"{PACSServer.__module__}.threading.Thread") as mock_thread,
    ):
        # Simulate KeyboardInterrupt when joining threads
        mock_thread.return_value.join.side_effect = KeyboardInterrupt()

        main()

        cast(Mock, mock_pacs.return_value).stop.assert_called_once()
        cast(Mock, mock_mwl.return_value).stop.assert_called_once()
