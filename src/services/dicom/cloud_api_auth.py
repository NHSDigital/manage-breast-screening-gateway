"""Shared bearer-token acquisition for calls to the Rubie cloud API.

Deployed environments authenticate with the VM's managed identity against the
environment's web-API app registration (CLOUD_API_RESOURCE). Local development
falls back to the static CLOUD_API_TOKEN.
"""

import os

from azure.identity import ManagedIdentityCredential

from environment import Environment


def access_token() -> str | None:
    resource = os.getenv("CLOUD_API_RESOURCE", "")
    if resource or Environment().production:
        return ManagedIdentityCredential().get_token(resource).token
    return os.getenv("CLOUD_API_TOKEN", "")


def auth_headers() -> dict:
    return {"Authorization": f"Bearer {access_token()}"}
