"""
Read-only dry run of the 09:18 unconditional exit, using real Jainam
(XTS) data -- Market Data API only, no Interactive API required.

This project never places real orders, so there is no real broker
position to query in the first place. Instead, it reads positions.json
(written by the most recent dry_run_entry.py run -- see
position_store.py) to know what position would exist, instrument
tokens included, then fetches the CURRENT live price for those same
legs. No signal replay, no re-resolving instruments: entry already did
that work and persisted it.

DOES NOT PLACE, MODIFY, OR CANCEL ANY ORDER. There is deliberately NO
P&L check and NO stop loss -- per spec, the real exit is unconditional
square-off, no conditions.

Run at/after 09:18 IST for the "price at square-off" number to be
meaningful; it'll still run at other times, just quoting whatever the
current live price is instead.

    .venv/bin/python jainam/scripts/dry_run_exit.py
"""

import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from jainam.broker.xts_client import XTSDataClient
from position_store import read_position

IST = ZoneInfo("Asia/Kolkata")


def _previous_trading_day(d: date) -> date:
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:  # Sat/Sun, calendar-only -- no NSE holiday calendar
        prev -= timedelta(days=1)
    return prev


def main() -> None:
    now_ist = datetime.now(IST)
    today = now_ist.date()
    print(f"=== DRY RUN EXIT -- Jainam/XTS (no orders placed) --- {now_ist.isoformat()} ===\n")

    position = read_position()
    if position is None:
        print("No positions.json found -- dry_run_entry.py hasn't been run yet. Nothing to exit.")
        return

    entry_date = date.fromisoformat(position["entry_date"])
    expected_entry_date = _previous_trading_day(today)
    if entry_date != expected_entry_date:
        print(
            f"NOTE: positions.json is from {entry_date}, but the expected prior trading day is "
            f"{expected_entry_date} -- this may be stale (entry didn't run, or already exited)."
        )
        print("Showing it anyway, read-only:\n")

    if not position["traded"]:
        print(f"{entry_date}: no trade was taken ({position['reason']}) -- nothing to exit.")
        return

    print(f"Position from {entry_date}: direction={position['direction']}, option_type={position['option_type']}, expiry={position['expiry']}")
    for leg in position["legs"]:
        print(f"  {leg['role']}: {leg['tradingsymbol']} strike {leg['strike']} qty {leg['quantity']}")

    client = XTSDataClient.from_env()

    print("\n=== Would square off now (unconditional, no P&L check) ===")
    for leg in position["legs"]:
        current_price = client.get_option_ltp(leg["instrument_token"])
        side = "SELL" if leg["role"] == "LONG_ATM" else "BUY"
        print(
            f"  {leg['tradingsymbol']}: qty {leg['quantity']} -> {side} {leg['quantity']} to close "
            f"@ current LTP {current_price}"
        )

    print("\nNo order was placed. This was a read-only dry run.")


if __name__ == "__main__":
    main()
