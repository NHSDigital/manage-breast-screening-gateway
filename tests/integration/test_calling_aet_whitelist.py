import pytest
from pynetdicom import AE
from pynetdicom.sop_class import (  # pyright: ignore[reportAttributeAccessIssue]
    ModalityWorklistInformationFind,
    Verification,
)

from server import MWLServer, PACSServer


@pytest.mark.integration
class TestMWLCallingAETWhitelist:
    @pytest.fixture(autouse=True)
    def with_mwl_server(self, tmp_dir):
        server = MWLServer(
            "MWL_SCP", 4243, f"{tmp_dir}/test.db", block=False, allowed_calling_aets=["ALLOWED_MODALITY"]
        )
        server.start()

        yield

        server.stop()

    def test_association_from_allowed_calling_aet_is_established(self):
        """Association from an allowed calling AE title is established."""
        ae = AE(ae_title="ALLOWED_MODALITY")
        ae.add_requested_context(ModalityWorklistInformationFind)
        assoc = ae.associate("127.0.0.1", 4243, ae_title="MWL_SCP")

        assert assoc.is_established
        assoc.release()

    def test_association_from_unknown_calling_aet_is_rejected(self):
        """Association from a calling AE title outside the allow list is rejected."""
        ae = AE(ae_title="UNKNOWN_MODALITY")
        ae.add_requested_context(ModalityWorklistInformationFind)
        assoc = ae.associate("127.0.0.1", 4243, ae_title="MWL_SCP")

        assert assoc.is_rejected
        assert not assoc.is_established


@pytest.mark.integration
class TestPACSCallingAETWhitelist:
    @pytest.fixture(autouse=True)
    def with_pacs_server(self, tmp_dir):
        server = PACSServer(
            "SCREENING_PACS",
            4244,
            tmp_dir,
            f"{tmp_dir}/test.db",
            block=False,
            mwl_db_path=f"{tmp_dir}/worklist.db",
            allowed_calling_aets=["ALLOWED_MODALITY"],
        )
        server.start()

        yield

        server.stop()

    def test_association_from_allowed_calling_aet_is_established(self):
        """Association from an allowed calling AE title is established."""
        ae = AE(ae_title="ALLOWED_MODALITY")
        ae.add_requested_context(Verification)
        assoc = ae.associate("127.0.0.1", 4244, ae_title="SCREENING_PACS")

        assert assoc.is_established
        assoc.release()

    def test_association_from_unknown_calling_aet_is_rejected(self):
        """Association from a calling AE title outside the allow list is rejected."""
        ae = AE(ae_title="UNKNOWN_MODALITY")
        ae.add_requested_context(Verification)
        assoc = ae.associate("127.0.0.1", 4244, ae_title="SCREENING_PACS")

        assert assoc.is_rejected
        assert not assoc.is_established
