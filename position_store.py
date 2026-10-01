"""
Minimal JSON-backed position store shared by the entry/exit scripts.

mode "dry"  = what a dry run computed; nothing was traded.
mode "live" = real orders were placed; legs carry the ACTUAL filled
              quantity and average price.
status      = "OPEN" until the live exit has closed every leg, then "CLOSED".

The live exit only acts on mode "live" + status "OPEN", so a dry-run
file can never cause a real order.

positions.json lives at the repo root and is gitignored -- it's local
run state, not source.
"""

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
POSITIONS_PATH = Path(__file__).resolve().parent / "positions.json"


@dataclass(frozen=True)
class PositionLeg:
    role: str
    strike: float
    instrument_token: int
    tradingsymbol: str
    quantity: int
    avg_price: float = 0.0  # actual fill price (live only)


def write_no_trade(entry_date: date, reason: str, mode: str = "dry") -> None:
    _write(
        {
            "entry_date": entry_date.isoformat(),
            "mode": mode,
            "traded": False,
            "reason": reason,
            "written_at": datetime.now(IST).isoformat(),
        }
    )


def write_position(
    entry_date: date,
    direction: str,
    option_type: str,
    expiry: date,
    legs: list[PositionLeg],
    mode: str = "dry",
    status: str = "OPEN",
) -> None:
    _write(
        {
            "entry_date": entry_date.isoformat(),
            "mode": mode,
            "status": status,
            "traded": True,
            "direction": direction,
            "option_type": option_type,
            "expiry": expiry.isoformat(),
            "legs": [asdict(leg) for leg in legs],
            "closed_roles": [],
            "written_at": datetime.now(IST).isoformat(),
        }
    )


def update_position(**fields) -> None:
    """Merge fields into the stored position (e.g. closed_roles, status)."""
    data = read_position()
    if data is None:
        raise RuntimeError("No positions.json to update")
    data.update(fields)
    data["updated_at"] = datetime.now(IST).isoformat()
    _write(data)


def read_position() -> dict | None:
    """Returns the stored position dict, or None if no file exists yet."""
    if not POSITIONS_PATH.exists():
        return None
    return json.loads(POSITIONS_PATH.read_text())


def _write(data: dict) -> None:
    tmp = POSITIONS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    tmp.replace(POSITIONS_PATH)  # atomic: a crash can't leave a half-written file
