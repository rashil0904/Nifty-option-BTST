"""
Read-only dry run of the 09:18 unconditional exit, using real Kite data.

DOES NOT PLACE, MODIFY, OR CANCEL ANY ORDER. It fetches current open
NIFTY option positions from the broker and prints what would be
squared off. There is deliberately NO P&L check and NO stop loss --
per spec, the real exit is unconditional square-off, next trading day.

Run at/after 09:18 IST.

    .venv/bin/python scripts/dry_run_exit.py
"""

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from broker.kite_client import KiteDataClient

IST = ZoneInfo("Asia/Kolkata")


def main() -> None:
    now_ist = datetime.now(IST)
    print(f"=== DRY RUN EXIT (no orders placed) --- {now_ist.isoformat()} ===\n")

    client = KiteDataClient.from_env()
    positions = client.get_open_nifty_option_positions()

    if not positions:
        print("No open NIFTY option positions found -- nothing to square off.")
        return

    print("=== Would square off now (unconditional, no P&L check) ===")
    for pos in positions:
        side = "SELL" if pos["quantity"] > 0 else "BUY"
        print(
            f"  {pos['tradingsymbol']}: qty {pos['quantity']} -> "
            f"{side} {abs(pos['quantity'])} to close"
        )

    print("\nNo order was placed. This was a read-only dry run.")


if __name__ == "__main__":
    main()
