"""Tests for DIMSE Message ID allocation."""

import itertools
import threading

import services.dicom as dicom
from services.dicom import MAX_MESSAGE_ID, next_message_id


def test_next_message_id_returns_distinct_16_bit_values():
    """Consecutive requests receive distinct, valid Message IDs."""
    ids = [next_message_id() for _ in range(100)]

    assert len(set(ids)) == len(ids)
    assert all(1 <= msg_id <= MAX_MESSAGE_ID for msg_id in ids)


def test_next_message_id_is_thread_safe():
    """Concurrent allocation never returns the same Message ID twice."""
    ids: list[int] = []
    results_lock = threading.Lock()

    def allocate() -> None:
        for _ in range(50):
            msg_id = next_message_id()
            with results_lock:
                ids.append(msg_id)

    threads = [threading.Thread(target=allocate) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(ids) == 400
    assert len(set(ids)) == 400


def test_next_message_id_wraps_after_maximum(monkeypatch):
    """The 16-bit counter wraps from 65535 back to 1."""
    monkeypatch.setattr(dicom, "_message_id_counter", itertools.count(MAX_MESSAGE_ID))

    assert next_message_id() == MAX_MESSAGE_ID
    assert next_message_id() == 1
