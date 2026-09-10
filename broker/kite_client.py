"""
Read-only Zerodha Kite Connect data layer.

Deliberately no order placement/status/cancel here yet -- this is the
dry-run/data-fetch phase only. All methods either return real data or
raise clearly; nothing here guesses a symbol or silently falls back.
"""

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from dotenv import load_dotenv
from kiteconnect import KiteConnect

IST_CANDLE_TZ_NOTE = (
    "Kite historical_data() timestamps a 1-minute candle by its START "
    "time (e.g. the record for 15:14 covers 15:14:00-15:15:00). This is "
    "Kite's documented convention but MUST be empirically re-verified "
    "against a known historical value before trusting it live -- see "
    "scripts/verify_candle_convention.py."
)


class InstrumentNotFoundError(Exception):
    """Raised when a required instrument can't be resolved. Never guess a symbol."""


class CandleNotFoundError(Exception):
    """Raised when the expected candle isn't present in the historical data response."""


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


class KiteDataClient:
    def __init__(self, api_key: str, access_token: str):
        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)
        self._nfo_instruments_cache = None

    @classmethod
    def from_env(cls, env_path: str | None = None) -> "KiteDataClient":
        load_dotenv(env_path)
        api_key = os.environ.get("KITE_API_KEY")
        access_token = os.environ.get("KITE_ACCESS_TOKEN")
        if not api_key:
            raise RuntimeError("KITE_API_KEY not set in .env")
        if not access_token:
            raise RuntimeError(
                "KITE_ACCESS_TOKEN not set in .env -- run scripts/kite_login.py first"
            )
        return cls(api_key=api_key, access_token=access_token)

    # --- VIX -----------------------------------------------------------

    INDIA_VIX_INSTRUMENT_TOKEN = 264969  # NSE:INDIA VIX index

    def get_india_vix(self) -> float:
        """Live VIX quote -- only meaningful for 'now', not historical replay."""
        quote = self.kite.quote(["NSE:INDIA VIX"])
        try:
            return float(quote["NSE:INDIA VIX"]["last_price"])
        except KeyError as exc:
            raise InstrumentNotFoundError("NSE:INDIA VIX not found in quote response") from exc

    def get_historical_vix_at_1515(self, target_date: date) -> float:
        """
        Approximate "VIX at 15:15" for a past date using the close of the
        15:14 candle (the last settled value before/at that moment) --
        same convention as the Nifty Fut 15:14 read, for consistency.
        """
        return self.get_candle_at(
            self.INDIA_VIX_INSTRUMENT_TOKEN, target_date, time(15, 14)
        ).close

    # --- instrument master ----------------------------------------------

    def _nfo_instruments(self) -> list[dict]:
        if self._nfo_instruments_cache is None:
            self._nfo_instruments_cache = self.kite.instruments("NFO")
        return self._nfo_instruments_cache

    def get_nifty_fut_instrument(self, as_of: date) -> dict:
        """
        Resolve the current (nearest-unexpired) NIFTY futures contract as
        of the given date. Raises if none found.
        """
        candidates = [
            row
            for row in self._nfo_instruments()
            if row["name"] == "NIFTY"
            and row["instrument_type"] == "FUT"
            and row["segment"] == "NFO-FUT"
            and row["expiry"] >= as_of
        ]
        if not candidates:
            raise InstrumentNotFoundError(f"No NIFTY future found with expiry >= {as_of}")
        candidates.sort(key=lambda row: row["expiry"])
        return candidates[0]

    def resolve_nifty_option_grid(self, expiry: date) -> tuple[float, int]:
        """
        Return (strike_interval, lot_size) for NIFTY options at the given
        expiry, derived from the live instrument master. Raises if the
        expiry has no listed option strikes.
        """
        rows = [
            row
            for row in self._nfo_instruments()
            if row["name"] == "NIFTY"
            and row["segment"] == "NFO-OPT"
            and row["expiry"] == expiry
        ]
        if not rows:
            raise InstrumentNotFoundError(f"No NIFTY options found for expiry {expiry}")
        strikes = sorted({row["strike"] for row in rows})
        if len(strikes) < 2:
            raise InstrumentNotFoundError(
                f"Fewer than 2 strikes listed for NIFTY expiry {expiry}; cannot derive interval"
            )
        diffs = [round(b - a, 2) for a, b in zip(strikes, strikes[1:])]
        strike_interval = min(diffs)
        lot_size = rows[0]["lot_size"]
        return strike_interval, lot_size

    def resolve_option_instrument(self, strike: float, option_type: str, expiry: date) -> dict:
        """
        Resolve the exact NIFTY option instrument (tradingsymbol,
        instrument_token, etc.) for the given strike/type/expiry.
        Raises InstrumentNotFoundError if it doesn't exist -- never
        guesses a symbol.
        """
        if option_type not in ("CE", "PE"):
            raise ValueError(f"option_type must be CE or PE, got {option_type!r}")
        matches = [
            row
            for row in self._nfo_instruments()
            if row["name"] == "NIFTY"
            and row["segment"] == "NFO-OPT"
            and row["expiry"] == expiry
            and row["instrument_type"] == option_type
            and row["strike"] == strike
        ]
        if not matches:
            raise InstrumentNotFoundError(
                f"No NIFTY {option_type} found for strike={strike} expiry={expiry}"
            )
        if len(matches) > 1:
            raise InstrumentNotFoundError(
                f"Ambiguous: {len(matches)} NIFTY {option_type} instruments found for "
                f"strike={strike} expiry={expiry}"
            )
        return matches[0]

    # --- candles ---------------------------------------------------------

    def get_candle_at(self, instrument_token: int, target_date: date, target_time: time) -> Candle:
        """
        Fetch the 1-minute candle whose start timestamp is exactly
        target_date + target_time. Raises CandleNotFoundError if the
        historical data response doesn't contain that exact minute
        (e.g. queried before market data for that minute exists).
        """
        from_dt = datetime.combine(target_date, time(9, 0))
        to_dt = datetime.combine(target_date, time(15, 30))
        records = self.kite.historical_data(
            instrument_token, from_dt, to_dt, interval="minute"
        )
        target_dt = datetime.combine(target_date, target_time)
        for row in records:
            row_dt = row["date"].replace(tzinfo=None)
            if row_dt == target_dt:
                return Candle(
                    timestamp=row_dt,
                    open=row["open"],
                    high=row["high"],
                    low=row["low"],
                    close=row["close"],
                )
        raise CandleNotFoundError(
            f"No candle found starting at {target_dt} for instrument {instrument_token} "
            f"({len(records)} candles returned in range)"
        )

    def get_nifty_fut_open_0915(self, target_date: date, instrument_token: int) -> float:
        return self.get_candle_at(instrument_token, target_date, time(9, 15)).open

    def get_nifty_fut_1514_close(self, target_date: date, instrument_token: int) -> float:
        return self.get_candle_at(instrument_token, target_date, time(15, 14)).close

    # --- spot (for ATM strike selection) ----------------------------------

    NIFTY_SPOT_INSTRUMENT_TOKEN = 256265  # NSE:NIFTY 50 index

    def get_nifty_spot_1514_close(self, target_date: date) -> float:
        """
        Nifty 50 spot index close of the 15:14 candle. Used for ATM strike
        selection -- options are struck relative to spot, not the future,
        since the future can trade at a premium/discount to spot (basis).
        Direction signal still uses the Future (unchanged), only ATM/OTM
        strike selection uses this.
        """
        return self.get_candle_at(
            self.NIFTY_SPOT_INSTRUMENT_TOKEN, target_date, time(15, 14)
        ).close
