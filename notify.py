"""
Telegram alerts for live entry/exit events.

Best-effort by design: a notification failure must never fail a real
trade. `notify()` swallows any error and just prints a warning --
every live_entry.py/live_exit.py call site uses that, never
send_telegram_message() directly, except where explicitly testing the
credentials.

Deliberately does NOT call load_dotenv() itself -- this module lives
at the repo root, and python-dotenv's default search anchors to the
*calling* file's directory. live_entry.py/live_exit.py live under
jainam/scripts/ and already call load_dotenv() themselves before
anything else runs, which correctly discovers jainam/.env (searching
upward from jainam/scripts/ through jainam/). Calling load_dotenv()
again from here would anchor to this file's own directory (repo root,
no .env there) instead -- harmless once the caller already loaded it,
but wrong if this were ever used before that happened. Reading
os.environ directly sidesteps the whole issue.
"""

import os

import requests


def send_telegram_message(text: str) -> None:
    """Raises on failure -- use notify() from live scripts instead."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set in .env")
    response = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")


def notify(text: str) -> None:
    """Send, but never raise -- a trade that succeeded must be reported as
    succeeded even if Telegram is down."""
    try:
        send_telegram_message(text)
    except Exception as exc:  # noqa: BLE001 -- alerting must never fail a real trade
        print(f"    WARNING: Telegram notify failed ({exc})")
