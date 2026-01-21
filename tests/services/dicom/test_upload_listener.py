from unittest.mock import Mock

import pytest

from services.dicom.upload_listener import UploadListener


@pytest.fixture
def mock_processor():
    processor = Mock()
    processor.backoff_delay = 0.0
    return processor


class TestUploadListener:
    def test_start_calls_process_batch(self, mock_processor):
        listener = UploadListener(
            processor=mock_processor,
            poll_interval=0.01,
            batch_size=10,
        )

        call_count = 0

        def stop_after_calls(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                listener.stop()

        mock_processor.process_batch.side_effect = stop_after_calls

        listener.start()

        assert mock_processor.process_batch.call_count == 3
        mock_processor.process_batch.assert_called_with(limit=10)

    def test_stop_sets_running_false(self, mock_processor):
        listener = UploadListener(processor=mock_processor)
        listener._running = True

        listener.stop()

        assert listener._running is False
