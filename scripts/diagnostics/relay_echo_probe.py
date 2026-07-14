#!/usr/bin/env python3
"""Standalone Azure Relay sender probe.

Connects to a Hybrid Connection as a sender (exactly like Manage does),
sends an `echo` action, and waits for the gateway relay listener's reply.
The listener answers echo actions without touching its database, so this
is a safe end-to-end test of the relay -> gateway dispatch path that
bypasses Manage entirely.

Usage:
    pip install websockets
    python relay_echo_probe.py \
        --namespace relay-manbrs-prod.servicebus.windows.net \
        --hc hc-gw-hull-university-teaching-hospitals-nhs-trust-rwa-01 \
        --key-name RootManageSharedAccessKey \
        --key '<key from portal: relay namespace -> Shared access policies>'

Interpreting the output:
    CONNECTED + RESPONSE  -> relay dispatch to the gateway works; the fault
                             is specific to Manage's sender connection.
    CONNECTED + TIMEOUT   -> same failure as Manage: the relay accepts the
                             sender but the listener never receives the
                             rendezvous. Fault is relay<->listener side.
    CONNECT FAILED        -> note the HTTP status: 404 = no listener /
                             wrong HC name; 401 = bad token (the per-HC
                             "listen" policy key cannot send - use the
                             namespace-level RootManageSharedAccessKey).

Running the equivalent probe from INSIDE the Manage container tests Manage's
actual network path, DNS resolution and managed identity (a laptop probe can
succeed while the container is broken - e.g. private DNS hijacking the relay
hostname inside the VNet, which is how the July 2026 outage was found):

    az containerapp exec -n <app-name> -g <resource-group> --command sh

    # 1. What does the relay hostname resolve to? Must be a PUBLIC IP.
    /app/.venv/bin/python -c "import socket; print(socket.getaddrinfo(
        'relay-manbrs-prod.servicebus.windows.net', 443)[0][4])"

    # 2. Echo through the app's own Relay record, token and code:
    /app/.venv/bin/python /app/manage.py shell -c "
    import json
    from manage_breast_screening.gateway.models import Relay
    from manage_breast_screening.gateway.relay_service import RelayURI
    from websockets.sync.client import connect
    url = RelayURI(Relay.objects.first()).connection_url()
    with connect(url, compression=None, open_timeout=30) as ws:
        ws.send(json.dumps({'action_type': 'echo', 'timestamp': 'probe'}))
        print('RESPONSE:', ws.recv(timeout=35))
    "

Note: manage.py shell is NOT gevent-patched, so a shell probe passing does not
prove the deployed request path works (see ADR-009 in the Manage repo). The
definitive Manage-side test is a real check-in from the web UI.
"""

import argparse
import base64
import hashlib
import hmac
import json
import sys
import time
import urllib.parse
from datetime import datetime, timezone

try:
    from websockets.sync.client import connect
except ImportError:
    sys.exit("Please `pip install websockets` (needs version 12+ for the sync client).")

RECEIVE_TIMEOUT_SECONDS = 35  # a little over Manage's 30s so we mirror its failure mode


def create_sas_token(namespace: str, hc_name: str, key_name: str, key: str) -> str:
    # Mirrors Manage's RelayURI._create_sas_token
    uri = f"https://{namespace}/{hc_name}"
    encoded_uri = urllib.parse.quote_plus(uri)
    expiry = str(int(time.time() + 3600))
    signature = base64.b64encode(hmac.new(key.encode(), f"{encoded_uri}\n{expiry}".encode(), hashlib.sha256).digest())
    return f"SharedAccessSignature sr={encoded_uri}&sig={urllib.parse.quote_plus(signature)}&se={expiry}&skn={key_name}"


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Azure Relay sender echo probe")
    parser.add_argument("--namespace", required=True, help="e.g. relay-manbrs-prod.servicebus.windows.net")
    parser.add_argument("--hc", required=True, help="hybrid connection name, e.g. hc-gw-...-rwa-01")
    parser.add_argument("--key-name", default="RootManageSharedAccessKey")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--key", help="shared access key value")
    group.add_argument(
        "--bearer-token",
        help=(
            "AAD access token for the relay, to test the bearer path Manage uses "
            "in production. Requires the caller to hold Azure Relay Sender. "
            "Get one with: az account get-access-token --resource https://relay.azure.net --query accessToken -o tsv"
        ),
    )
    args = parser.parse_args()

    if args.bearer_token:
        token = f"Bearer {args.bearer_token}"
    else:
        token = create_sas_token(args.namespace, args.hc, args.key_name, args.key)
    url = f"wss://{args.namespace}/$hc/{args.hc}?sb-hc-action=connect&sb-hc-token={urllib.parse.quote_plus(token)}"

    payload = {
        "action_type": "echo",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "relay_echo_probe",
    }

    log(f"Connecting as sender to wss://{args.namespace}/$hc/{args.hc} ...")
    started = time.monotonic()
    try:
        with connect(url, compression=None, open_timeout=30) as ws:
            log(f"CONNECTED in {time.monotonic() - started:.1f}s - sending echo action...")
            ws.send(json.dumps(payload))
            log(f"Sent. Waiting up to {RECEIVE_TIMEOUT_SECONDS}s for the gateway's reply...")
            try:
                response = ws.recv(timeout=RECEIVE_TIMEOUT_SECONDS)
            except TimeoutError:
                log("TIMEOUT - no response from the gateway listener.")
                log("=> Same failure as Manage: relay accepted the sender but the")
                log("   listener never answered. Fault is on the relay<->listener side.")
                return 2
            log(f"RESPONSE received in {time.monotonic() - started:.1f}s total:")
            print(json.dumps(json.loads(response), indent=2))
            log("=> Relay dispatch to the gateway WORKS. The fault is specific to")
            log("   Manage's sender connection.")
            return 0
    except Exception as e:
        log(f"CONNECT FAILED after {time.monotonic() - started:.1f}s: {type(e).__name__}: {e}")
        response = getattr(e, "response", None)
        if response is not None:
            for header in ("x-ms-error-code", "www-authenticate", "trackingid"):
                value = response.headers.get(header)
                if value:
                    log(f"   {header}: {value}")
            body = getattr(response, "body", b"")
            if body:
                log(f"   body: {body.decode('utf-8', errors='replace')[:500]}")
        log("=> 404 means no listener / wrong HC name; 401 means bad token/key")
        log("   (note: each HC also has a listen-only policy - its key cannot send;")
        log("   use the namespace-level RootManageSharedAccessKey).")
        return 1


if __name__ == "__main__":
    sys.exit(main())
