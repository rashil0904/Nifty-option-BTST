"""
Minimal JSON-backed position store shared by the entry/exit dry-run
scripts.

This project never places real orders -- "position" here means "what
the entry dry run most recently computed," not a broker-confirmed
fill. Entry writes it; exit reads it directly instead of replaying
historical signals or re-resolving instruments from scratch.

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


def write_no_trade(entry_date: date, reason: str) -> None:
    _write(
        {
            "entry_date": entry_date.isoformat(),
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
) -> None:
    _write(
        {
            "entry_date": entry_date.isoformat(),
            "traded": True,
            "direction": direction,
            "option_type": option_type,
            "expiry": expiry.isoformat(),
            "legs": [asdict(leg) for leg in legs],
            "written_at": datetime.now(IST).isoformat(),
        }
    )


def read_position() -> dict | None:
    """Returns the stored position dict, or None if no file exists yet."""
    if not POSITIONS_PATH.exists():
        return None
    return json.loads(POSITIONS_PATH.read_text())


def _write(data: dict) -> None:
    POSITIONS_PATH.write_text(json.dumps(data, indent=2) + "\n")
