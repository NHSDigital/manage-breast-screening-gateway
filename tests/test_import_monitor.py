from unittest.mock import MagicMock, patch

import import_monitor


def test_import_monitor_processes_json_files():
    imports = []

    class FakeStorage:
        def __init__(self, db_path):
            self.db_path = db_path

    with (
        patch.object(import_monitor.config, "import_directory", return_value="/tmp/imports"),
        patch.object(import_monitor.config, "import_poll_interval", return_value=0.01),
        patch.object(import_monitor.config, "mwl_db_path", return_value="/tmp/mwl.db"),
        patch.object(import_monitor, "MWLStorage", FakeStorage),
        patch.object(import_monitor, "ClinicImporter") as mock_importer,
        patch.object(import_monitor.os, "makedirs"),
        patch.object(import_monitor.os.path, "exists", return_value=True),
        patch.object(
            import_monitor.glob,
            "glob",
            return_value=[
                "/tmp/imports/a.json",
                "/tmp/imports/b.json",
            ],
        ),
    ):
        monitor = import_monitor.ImportMonitor()

        assert monitor.import_directory == "/tmp/imports"
        assert monitor.poll_interval == 0.01
        assert monitor.storage.db_path == "/tmp/mwl.db"

        monitor.check_for_new_files()

    mock_importer.assert_any_call(monitor.storage, {"source": "file", "file_path": "/tmp/imports/a.json"})
    mock_importer.assert_any_call(monitor.storage, {"source": "file", "file_path": "/tmp/imports/b.json"})
