#!/bin/bash

uv run python -m pacs_main &

uv run python -m mwl_main &

uv run python -m src.relay_listener &

uv run python -m upload_main &

# Wait for any process to exit
wait -n

# Exit with status of process that exited first
exit $?
