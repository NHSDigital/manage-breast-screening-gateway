import json
import os
from unittest.mock import MagicMock, patch

import pytest

from services.clinic_importer import ClinicImporter


@patch("services.clinic_importer.CreateWorklistItem")
class TestClinicImporter:
    @patch("services.clinic_importer.ManagedIdentityCredential")
    @patch("services.clinic_importer.requests.get")
    def test_import_from_api(self, mock_get, mock_credential, create_worklist_item_mock):
        storage = MagicMock()
        options = {
            "source": "api",
            "api_url": "https://example.test/clinic",
            "timeout": 5,
            "verify_ssl": False,
        }
        importer = ClinicImporter(storage, options)

        response = MagicMock()
        response.json.return_value = {"worklist_items": [{"id": 1}, {"id": 2}]}
        mock_create_worklist_item = create_worklist_item_mock.return_value
        mock_get.return_value = response

        importer.import_from_api()

        mock_get.assert_called_once_with(
            "https://example.test/clinic",
            timeout=5,
            verify=False,
            headers={"Authorization": f"Bearer {importer.access_token}"},
        )

        create_worklist_item_mock.assert_called_with(storage)
        mock_create_worklist_item.call.assert_any_call({"id": 1})
        mock_create_worklist_item.call.assert_any_call({"id": 2})

    def test_import_from_file(self, create_worklist_item_mock, tmp_path):
        storage = object()
        options = {
            "source": "file",
            "file_path": str(tmp_path / "clinic.json"),
        }

        mock_create_worklist_item = create_worklist_item_mock.return_value
        importer = ClinicImporter(storage, options)

        payload = {"worklist_items": [{"id": "a"}, {"id": "b"}]}
        (tmp_path / "clinic.json").write_text(json.dumps(payload), encoding="utf-8")

        importer.import_from_file()

        create_worklist_item_mock.assert_called_with(storage)
        mock_create_worklist_item.call.assert_any_call({"id": "a"})
        mock_create_worklist_item.call.assert_any_call({"id": "b"})

        assert os.path.exists(f"{options['file_path']}.processed")

    def test_import_data_rejects_invalid_options(self, create_worklist_item_mock):
        importer = ClinicImporter(object(), {"source": "unknown"})

        with pytest.raises(ValueError, match="Invalid import options"):
            importer.import_data()
