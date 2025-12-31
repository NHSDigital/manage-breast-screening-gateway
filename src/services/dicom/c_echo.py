import logging

from pynetdicom.events import Event

from services.dicom import SUCCESS

logger = logging.getLogger(__name__)


class CEcho:
    def call(self, event: Event):
        """Handle a C-ECHO request event (DICOM ping)."""
        logger.info("Received C-ECHO request")
        return SUCCESS
