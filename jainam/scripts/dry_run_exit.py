"""
Read-only dry run of the 09:18 unconditional exit, using real Jainam
(XTS) data. Mirrors scripts/dry_run_exit.py (the Kite version).

DOES NOT PLACE, MODIFY, OR CANCEL ANY ORDER. It fetches current open
NIFTY option positions from the broker and prints what would be
squared off. There is deliberately NO P&L check and NO stop loss --
per spec, the real exit is unconditional square-off, next trading day.

Run at/after 09:18 IST.

    .venv/bin/python jainam/scripts/dry_run_exit.py
"""

import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from jainam.broker.xts_client import XTSDataClient

IST = ZoneInfo("Asia/Kolkata")


def main() -> None:
    now_ist = datetime.now(IST)
    print(f"=== DRY RUN EXIT -- Jainam/XTS (no orders placed) --- {now_ist.isoformat()} ===\n")

    client = XTSDataClient.from_env()
    positions = client.get_open_nifty_option_positions()

    if not positions:
        print("No open NIFTY option positions found -- nothing to square off.")
        return

    print("=== Would square off now (unconditional, no P&L check) ===")
    for pos in positions:
        qty = pos["Quantity"]
        side = "SELL" if qty > 0 else "BUY"
        print(f"  {pos['TradingSymbol']}: qty {qty} -> {side} {abs(qty)} to close")

    print("\nNo order was placed. This was a read-only dry run.")


if __name__ == "__main__":
    main()
