"""DICOM services for PACS functionality."""

import itertools
import threading

# DICOM character sets
CHARSET_UTF8 = "ISO_IR 192"

# DIMSE Message ID (0000,0110) is a 16-bit US value used to distinguish
# concurrent messages on an association. Allocate IDs from a thread-safe
# process-wide counter, which is stricter than the per-association requirement.
MAX_MESSAGE_ID = 0xFFFF
_INITIAL_MESSAGE_ID = 1
_message_id_counter = itertools.count(_INITIAL_MESSAGE_ID)
_message_id_lock = threading.Lock()


def next_message_id() -> int:
    """Return the next Message ID for a DIMSE request, wrapping at 65535."""
    with _message_id_lock:
        return ((next(_message_id_counter) - _INITIAL_MESSAGE_ID) % MAX_MESSAGE_ID) + _INITIAL_MESSAGE_ID


# Used only when a handler event doesn't expose the request's command set.
DEFAULT_MESSAGE_ID = _INITIAL_MESSAGE_ID

# DICOM status codes
SUCCESS = 0x0000
FAILURE = 0xC000
PENDING = 0xFF00
PENDING_WARNING = 0xFF01
INVALID_ATTRIBUTE = 0x0106
DUPLICATE_SOP_INSTANCE = 0x0111
UNKNOWN_SOP_INSTANCE = 0x0112
MISSING_ATTRIBUTE = 0x0120
PROCESSING_FAILURE = 0x0110
REFUSED_NOT_AUTHORISED = 0x0124
