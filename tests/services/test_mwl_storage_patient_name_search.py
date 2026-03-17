"""
Integration-style tests for MWLStorage.find_worklist_items patient name filtering.

These tests use a real SQLite database to verify that wildcard conversion and case-insensitive
matching work correctly in practice.
"""

import pytest

from services.storage import MWLStorage, WorklistItem


@pytest.fixture
def storage(tmp_dir):
    return MWLStorage(f"{tmp_dir}/worklist.db")


@pytest.fixture(autouse=True)
def items(storage):
    """Insert a small set of worklist items with varied names."""
    names = [
        "SMITH^SARITA",
        "SMITH^JANE",
        "JONES^SARITA",
        "MÜLLER^DILMA",
    ]
    for i, name in enumerate(names):
        storage.store_worklist_item(
            WorklistItem(
                accession_number=f"ACC{i:03d}",
                patient_id=f"999000000{i}",
                patient_name=name,
                patient_birth_date="19800101",
                scheduled_date="20260101",
                scheduled_time="090000",
                modality="MG",
            )
        )
    return names


class TestPatientNameSearch:
    def test_trailing_wildcard(self, storage):
        results = storage.find_worklist_items(patient_name="SMITH*")
        assert {r.patient_name for r in results} == {"SMITH^SARITA", "SMITH^JANE"}

    def test_wildcard_on_given_name(self, storage):
        results = storage.find_worklist_items(patient_name="*SARITA")
        assert {r.patient_name for r in results} == {"SMITH^SARITA", "JONES^SARITA"}

    def test_single_character_wildcard(self, storage):
        results = storage.find_worklist_items(patient_name="SMITH^J?NE")
        assert {r.patient_name for r in results} == {"SMITH^JANE"}

    def test_exact_match(self, storage):
        results = storage.find_worklist_items(patient_name="JONES^SARITA")
        assert len(results) == 1
        assert results[0].patient_name == "JONES^SARITA"

    def test_no_match(self, storage):
        results = storage.find_worklist_items(patient_name="BROWN*")
        assert results == []

    def test_case_insensitive_match(self, storage):
        results = storage.find_worklist_items(patient_name="smith*")
        assert {r.patient_name for r in results} == {"SMITH^SARITA", "SMITH^JANE"}

    @pytest.mark.xfail(reason="SQLite's UPPER() is ASCII-only; non-ASCII case folding requires ICU compilation")
    def test_case_insensitive_non_ascii(self, storage):
        results = storage.find_worklist_items(patient_name="müller*")
        assert {r.patient_name for r in results} == {"MÜLLER^DILMA"}
