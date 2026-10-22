"""
Append-only local record of every CLOSED live BTST trade.

positions.json (position_store.py) only ever holds the CURRENT position --
it's overwritten on every entry and gitignored as local run state (see its
own docstring). Something has to accumulate the full history once a trade
closes, or there is no PnL to report at all. This file is that something:
one record appended per fully-closed trade, read by results/build_pnl.py
to regenerate the PnL workbook. Tracked in git, not gitignored -- same
choice volume-daily (the project this pattern is based on) makes for its
own positions_dhan_*.json: this is a permanent ledger, not transient run
state like positions.json.

trade_history.json lives alongside this file, at results/trade_history.json.
"""

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
HISTORY_PATH = Path(__file__).resolve().parent / "trade_history.json"


def _gross_pnl(legs: dict[str, dict]) -> float | None:
    long_leg = legs.get("LONG_ATM")
    short_leg = legs.get("SHORT_OTM")
    if not long_leg or not short_leg:
        return None
    if long_leg.get("exit_price") is None or short_leg.get("exit_price") is None:
        return None
    long_pnl = (long_leg["exit_price"] - long_leg["avg_price"]) * long_leg["quantity"]
    short_pnl = (short_leg["avg_price"] - short_leg["exit_price"]) * short_leg["quantity"]
    return round(long_pnl + short_pnl, 2)


def append_closed_trade(position: dict) -> dict:
    """position is the full positions.json dict once every leg has closed
    (status == "CLOSED", every leg carries exit_price/exit_timestamp --
    see position_store.record_leg_exit). Returns the record it wrote, so
    the caller can hand the same dict straight to push_to_sheet.push_trade
    without re-reading the file."""
    legs = {leg["role"]: leg for leg in position["legs"]}
    exit_dates = [leg["exit_timestamp"][:10] for leg in legs.values() if leg.get("exit_timestamp")]

    record = {
        "entry_date": position["entry_date"],
        "direction": position["direction"],
        "option_type": position["option_type"],
        "expiry": position["expiry"],
        "legs": legs,
        "exit_date": max(exit_dates) if exit_dates else None,
        "gross_pnl": _gross_pnl(legs),
        "archived_at": datetime.now(IST).isoformat(),
    }

    HISTORY_PATH.parent.mkdir(exist_ok=True)
    history = []
    if HISTORY_PATH.exists():
        try:
            history = json.loads(HISTORY_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            history = []
    history.append(record)

    tmp = HISTORY_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(history, indent=2) + "\n")
    tmp.replace(HISTORY_PATH)
    return record


def load_trade_history() -> list[dict]:
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return []
