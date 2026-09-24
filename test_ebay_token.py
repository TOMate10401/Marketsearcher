"""Isolated test for the eBay OAuth client-credentials grant against production.

Loads credentials from a local .env file (never committed), mints an
Application Access Token, and prints the result. Run with:

    python test_ebay_token.py
"""

import base64
import os

import requests


PRODUCTION_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"

DEFAULT_SCOPE = "https://api.ebay.com/oauth/api_scope"


def _load_env(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def _b64_credentials(client_id, client_secret):
    raw = f"{client_id}:{client_secret}".encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")


def get_application_token(
    client_id,
    client_secret,
    scope=DEFAULT_SCOPE,
    env="production",
):
    token_url = PRODUCTION_TOKEN_URL
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {_b64_credentials(client_id, client_secret)}",
    }
    data = {"grant_type": "client_credentials", "scope": scope}
    resp = requests.post(token_url, headers=headers, data=data, timeout=20)
    return resp


def main():
    _load_env()
    client_id = os.environ.get("EBAY_CLIENT_ID")
    client_secret = os.environ.get("EBAY_CLIENT_SECRET")
    env = os.environ.get("EBAY_ENV", "production")
    scope = os.environ.get("EBAY_SCOPE", DEFAULT_SCOPE)
    marketplace = os.environ.get("EBAY_MARKETPLACE_ID", "EBAY_DE")

    missing = [
        name for name, val in (
            ("EBAY_CLIENT_ID", client_id),
            ("EBAY_CLIENT_SECRET", client_secret),
        ) if not val
    ]
    if missing:
        print(f"MISSING env vars: {', '.join(missing)}")
        return

    print(f"Env:           {env}")
    print(f"Marketplace:   {marketplace}")
    print(f"Scope:         {scope}")
    print(f"Client ID:     {client_id[:14]}...{client_id[-4:]}")
    print(f"Token endpoint: {PRODUCTION_TOKEN_URL}")
    print("-" * 60)

    resp = get_application_token(client_id, client_secret, scope, env)
    print(f"HTTP status:   {resp.status_code}")
    try:
        body = resp.json()
    except ValueError:
        print(f"Response text:  {resp.text}")
        return

    if resp.status_code == 200:
        token = body.get("access_token", "")
        print("Token minted:  YES")
        print(f"Token type:    {body.get('token_type', '')}")
        print(f"Expires in:    {body.get('expires_in', '')} s")
        print(f"Token preview: {token[:20]}...{token[-8:] if len(token) > 28 else ''}")
    else:
        print("Token minted:  NO")
        print(f"Error:         {body.get('error', '')}")
        print(f"Description:   {body.get('error_description', '')}")


if __name__ == "__main__":
    main()
