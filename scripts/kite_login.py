"""
Interactive daily Kite Connect login helper.

Kite access tokens expire daily. Run this once each morning before
using any broker/kite_client.py functionality:

    .venv/bin/python scripts/kite_login.py

It will:
  1. Print a login URL.
  2. You open it, log into Zerodha (your credentials, not stored here),
     and get redirected to your app's redirect URL with a
     `request_token=...` query param.
  3. Paste that request_token back here when prompted.
  4. It exchanges it for an access_token and writes it into .env.

Nothing here places an order or touches any position -- this only
establishes a read/write-authenticated session for later use.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from kiteconnect import KiteConnect

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def main() -> None:
    load_dotenv(ENV_PATH)
    api_key = os.environ.get("KITE_API_KEY")
    api_secret = os.environ.get("KITE_API_SECRET")
    if not api_key or not api_secret:
        print("KITE_API_KEY / KITE_API_SECRET not set in .env", file=sys.stderr)
        sys.exit(1)

    kite = KiteConnect(api_key=api_key)
    print("1. Open this URL in a browser and log into Zerodha:\n")
    print(f"   {kite.login_url()}\n")
    print("2. After login you'll be redirected to your app's redirect URL.")
    print("   Copy the `request_token` query parameter from that URL.\n")

    request_token = input("Paste request_token here: ").strip()
    if not request_token:
        print("No request_token entered, aborting.", file=sys.stderr)
        sys.exit(1)

    session = kite.generate_session(request_token, api_secret=api_secret)
    access_token = session["access_token"]

    _write_access_token_to_env(access_token)
    print(f"\nAccess token saved to {ENV_PATH}. Valid until next Kite session expiry (~end of day).")


def _write_access_token_to_env(access_token: str) -> None:
    lines = ENV_PATH.read_text().splitlines() if ENV_PATH.exists() else []
    found = False
    for i, line in enumerate(lines):
        if line.startswith("KITE_ACCESS_TOKEN="):
            lines[i] = f"KITE_ACCESS_TOKEN={access_token}"
            found = True
            break
    if not found:
        lines.append(f"KITE_ACCESS_TOKEN={access_token}")
    ENV_PATH.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
