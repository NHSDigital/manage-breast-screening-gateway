import pytest
from models import WorklistItem


class TestWorklistItem:
    @pytest.fixture
    def result(self):
        return {
            "accession_number": "12345",
            "patient_id": "P001",
            "patient_name": "John Doe",
            "patient_birth_date": "1980-01-01",
            "patient_sex": "M",
            "scheduled_date": "2024-06-01",
            "scheduled_time": "10:00:00",
            "modality": "CT",
            "study_description": "CT Scan of the Chest",
            "procedure_code": "CT123",
            "status": "SCHEDULED",
            "study_instance_uid": "test-study-instance-uid",
            "source_message_id": "test-source-message-id",
            "source_system_url": "https://run-breast-screening.nhs.uk",
        }

    def test_worklist_item_creation(self, result):
        """Worklist item creation."""
        item = WorklistItem(**result)

        assert item.accession_number == result["accession_number"]
        assert item.patient_id == result["patient_id"]
        assert item.patient_name == result["patient_name"]
        assert item.patient_birth_date == result["patient_birth_date"]
        assert item.patient_sex == result["patient_sex"]
        assert item.scheduled_date == result["scheduled_date"]
        assert item.scheduled_time == result["scheduled_time"]
        assert item.modality == result["modality"]
        assert item.study_description == result["study_description"]
        assert item.procedure_code == result["procedure_code"]
        assert item.status == result["status"]
        assert item.study_instance_uid == result["study_instance_uid"]
        assert item.source_message_id == result["source_message_id"]
        assert item.source_system_url == result["source_system_url"]

    def test_worklist_item_with_valid_source_system_url_subdomain(self, result):
        """Worklist item with valid source system url subdomain."""
        result["source_system_url"] = "https://subdomain.run-breast-screening.nhs.uk"

        item = WorklistItem(**result)

        assert item.source_system_url == result["source_system_url"]

    def test_worklist_item_with_invalid_source_system_url_scheme(self, result):
        """Worklist item with invalid source system url scheme."""
        result["source_system_url"] = "ftp://invalid-url"

        with pytest.raises(ValueError):
            WorklistItem(**result)

    def test_worklist_item_with_invalid_source_system_url_domain(self, result):
        """Worklist item with invalid source system url domain."""
        result["source_system_url"] = "https://invalid-url.com"

        with pytest.raises(ValueError):
            WorklistItem(**result)

    def test_worklist_item_with_missing_source_system_url(self, result):
        """Worklist item with missing source system url."""
        del result["source_system_url"]

        item = WorklistItem(**result)
        assert item.source_system_url is None

    def test_worklist_item_with_missing_required_fields(self, result):
        """Worklist item with missing required fields."""
        del result["accession_number"]

        with pytest.raises(TypeError):
            WorklistItem(**result)
