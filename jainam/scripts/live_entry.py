"""
LIVE 15:20 entry -- PLACES REAL ORDERS on Jainam (client from JAINAM_CLIENT_ID).

Refuses to run unless JAINAM_LIVE=true in .env. Order of operations:
  1. BUY the ATM leg (2 lots). Wait for the fill.
  2. Only then SELL the OTM leg (1 lot).
Buying first means a failure at any point leaves you long (defined
risk), never naked short. Entry uses limit orders only: if the buy can't
fill, nothing is traded.

    python jainam/scripts/live_entry.py
"""

import os
import sys
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from dotenv import load_dotenv

from config import LONG_LEG_LOTS_PER_UNIT, MARKET_HOLIDAYS, SHORT_LEG_LOTS_PER_UNIT
from jainam.broker.order_exec import execute_order
from jainam.broker.xts_client import XTSDataClient
from jainam.entry_signal import NoTrade, compute_entry_signal
from position_store import PositionLeg, read_position, write_no_trade, write_position

IST = ZoneInfo("Asia/Kolkata")
# Starts at 15:19 (when the signal candle settles), ends 15:27 (same 3-minute
# safety buffer before the 15:30 close as before) -- moving entry 5 minutes
# later naturally shrinks the execution buffer from 13 to 8 minutes for the
# buy-then-sell sequence with retries.
ENTRY_WINDOW = (time(15, 19), time(15, 27))


def main() -> int:
    load_dotenv()
    now = datetime.now(IST)
    today = now.date()
    print(f"=== LIVE ENTRY --- {now.isoformat()} ===")

    if os.environ.get("JAINAM_LIVE", "").lower() != "true":
        print("JAINAM_LIVE is not 'true' in .env -> refusing to trade.")
        return 1
    if today.weekday() >= 5 or today in MARKET_HOLIDAYS:
        print("Weekend/market holiday -> nothing to do.")
        return 0
    if not (ENTRY_WINDOW[0] <= now.time() <= ENTRY_WINDOW[1]):
        print(f"Outside the entry window {ENTRY_WINDOW[0]}-{ENTRY_WINDOW[1]} IST -> refusing to trade.")
        return 1

    existing = read_position()
    if existing and existing.get("mode") == "live" and existing.get("traded") and existing.get("status") == "OPEN":
        print(f"A live position from {existing['entry_date']} is still OPEN (exit hasn't closed it) -> not entering.")
        return 1
    if existing and existing.get("mode") == "live" and existing.get("entry_date") == today.isoformat():
        print("Live entry already ran today -> not entering twice.")
        return 1

    client = XTSDataClient.from_env()
    if not client.client_id or not client.interactive_token:
        print(f"Interactive login / JAINAM_CLIENT_ID missing: {client._interactive_error}")
        return 1

    signal = compute_entry_signal(client, today)
    if isinstance(signal, NoTrade):
        print(f"NO TRADE: {signal.reason}")
        write_no_trade(today, signal.reason, mode="live")
        return 0

    long_leg = next(l for l in signal.legs if l["role"] == "LONG_ATM")
    short_leg = next(l for l in signal.legs if l["role"] == "SHORT_OTM")
    tag = f"BTST{today.strftime('%d%m')}"

    # --- leg 1: BUY ATM ---------------------------------------------------
    print(f"\n[1/2] BUY {long_leg['quantity']} {long_leg['tradingsymbol']}")
    buy = execute_order(
        client, long_leg["instrument_token"], "BUY", long_leg["quantity"], tag + "L", allow_market_fallback=False
    )
    if buy.filled == 0:
        reason = f"ATM buy did not fill ({buy.rejected_reason or 'no fill'}) -- nothing traded"
        print(f"!! {reason}")
        write_no_trade(today, reason, mode="live")
        return 1

    def leg_record(leg, fill):
        return PositionLeg(
            role=leg["role"],
            strike=leg["strike"],
            instrument_token=leg["instrument_token"],
            tradingsymbol=leg["tradingsymbol"],
            quantity=fill.filled,
            avg_price=fill.avg_price,
        )

    # Persist the long leg immediately so a crash can never orphan it.
    legs = [leg_record(long_leg, buy)]
    write_position(today, signal.direction, signal.option_type, signal.expiry, legs, mode="live")
    print(f"    bought {buy.filled} @ avg {buy.avg_price}")

    # Short leg sized to the ACTUAL filled long lots, keeping the 2:1 ratio.
    long_lots_filled = buy.filled // signal.lot_size
    short_lots = (long_lots_filled // LONG_LEG_LOTS_PER_UNIT) * SHORT_LEG_LOTS_PER_UNIT
    short_qty = short_lots * signal.lot_size
    if short_qty == 0:
        print("!! Long leg filled too small to pair a short leg -> holding the long leg only.")
        return 1
    if short_qty != short_leg["quantity"]:
        print(f"    scaling short leg to {short_qty} to match the {buy.filled} long fill")

    # --- leg 2: SELL OTM --------------------------------------------------
    print(f"\n[2/2] SELL {short_qty} {short_leg['tradingsymbol']}")
    sell = execute_order(
        client, short_leg["instrument_token"], "SELL", short_qty, tag + "S", allow_market_fallback=False
    )
    if sell.filled:
        legs.append(leg_record(short_leg, sell))
        write_position(today, signal.direction, signal.option_type, signal.expiry, legs, mode="live")
        print(f"    sold {sell.filled} @ avg {sell.avg_price}")
    if sell.filled < short_qty:
        print(
            f"!! Short leg incomplete ({sell.filled}/{short_qty}; {sell.rejected_reason or 'unfilled'}). "
            "You are LONG the ATM leg with a smaller/no short leg -- review manually."
        )
        return 1

    print("\nLIVE ENTRY COMPLETE.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
