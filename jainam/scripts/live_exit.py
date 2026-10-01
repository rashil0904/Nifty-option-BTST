"""
LIVE 09:18 exit -- PLACES REAL ORDERS on Jainam (client from JAINAM_CLIENT_ID).

Refuses to run unless JAINAM_LIVE=true. Closes ONLY the exact contracts
and quantities the live entry recorded in positions.json -- never "all
open positions", because other logins trade this same client account.

Order: BUY BACK the short OTM leg first, then SELL the long ATM leg.
Closing the short first removes the risky leg; if it can't be closed
the long leg is left in place (still covering it) and the run stops.
Unconditional: no P&L check, no stop loss. Limit orders at increasing
aggression, with a final market order so the exit actually happens.

    python jainam/scripts/live_exit.py
"""

import os
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv

from config import MARKET_HOLIDAYS
from jainam.broker.order_exec import execute_order
from jainam.broker.xts_client import XTSDataClient
from position_store import read_position, update_position

IST = ZoneInfo("Asia/Kolkata")
EXIT_WINDOW = (time(9, 15), time(10, 30))

# role -> (exit side, sign of the net position we expect to be holding)
CLOSE_ORDER = [("SHORT_OTM", "BUY", -1), ("LONG_ATM", "SELL", +1)]


def main() -> int:
    load_dotenv()
    now = datetime.now(IST)
    today = now.date()
    print(f"=== LIVE EXIT --- {now.isoformat()} ===")

    if os.environ.get("JAINAM_LIVE", "").lower() != "true":
        print("JAINAM_LIVE is not 'true' in .env -> refusing to trade.")
        return 1
    if today.weekday() >= 5 or today in MARKET_HOLIDAYS:
        print("Weekend/market holiday -> nothing to do (an open position waits for the next trading day).")
        return 0
    if not (EXIT_WINDOW[0] <= now.time() <= EXIT_WINDOW[1]):
        print(f"Outside the exit window {EXIT_WINDOW[0]}-{EXIT_WINDOW[1]} IST -> refusing to trade.")
        return 1

    position = read_position()
    if position is None or position.get("mode") != "live" or not position.get("traded"):
        print("No live position recorded -> nothing to exit.")
        return 0
    if position.get("status") != "OPEN":
        print(f"Live position from {position['entry_date']} is already {position.get('status')} -> nothing to exit.")
        return 0
    if position["entry_date"] >= today.isoformat():
        print(f"Position was entered today ({position['entry_date']}) -> exit is for the next trading day.")
        return 0

    client = XTSDataClient.from_env()
    if not client.client_id or not client.interactive_token:
        print(f"Interactive login / JAINAM_CLIENT_ID missing: {client._interactive_error}")
        return 1

    legs = {leg["role"]: leg for leg in position["legs"]}
    closed = set(position.get("closed_roles", []))
    tag = f"BTST{today.strftime('%d%m')}X"
    ok = True

    for role, side, sign in CLOSE_ORDER:
        leg = legs.get(role)
        if leg is None or role in closed:
            continue
        qty, token = leg["quantity"], leg["instrument_token"]

        # Cross-check against the real account before trading anything.
        net = client.get_net_quantity(token)
        print(f"\n{role}: {leg['tradingsymbol']} recorded qty {qty}, account net {net:+d}")
        if net * sign < qty:
            print(f"!! Account holds {net:+d} but {sign * qty:+d} was expected -> NOT trading this leg. Review manually.")
            ok = False
            break

        print(f"{side} {qty} {leg['tradingsymbol']}")
        fill = execute_order(client, token, side, qty, tag + role[0], allow_market_fallback=True)
        if not fill.complete:
            print(
                f"!! {role} closed only {fill.filled}/{qty} ({fill.rejected_reason or 'unfilled'}). "
                "Stopping -- remaining legs untouched. Review manually."
            )
            ok = False
            break
        print(f"    closed {fill.filled} @ avg {fill.avg_price}")
        closed.add(role)
        update_position(closed_roles=sorted(closed))

    if ok and closed >= set(legs):
        update_position(status="CLOSED")
        print("\nLIVE EXIT COMPLETE.")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
