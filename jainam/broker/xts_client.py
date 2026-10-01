"""
Read-only Jainam (XTS-based) market-data + positions layer.

Jainam white-labels Symphony Fintech's XTS Connect API. This talks to
the documented REST endpoints directly with `requests` -- it does not
vendor Symphony's own Python SDK (github.com/symphonyfintech/xts-pythonclient-api-sdk),
since that repo carries no open-source license despite being public.

Deliberately no order placement/status/cancel here yet -- this is the
dry-run/data-fetch phase only. All methods either return real data or
raise clearly; nothing here guesses a symbol or silently falls back.

VERIFIED against a live Jainam session on 2026-09-30/10-01 (base URL
https://smpd.jainam.in:3643) -- entry-side signal resolution runs
clean end-to-end against real data:
  - Market Data login path is `/apibinarymarketdata/auth/login` (the
    generic reference SDK's route table uses `/apimarketdata/...`
    without "binary" -- that's wrong for this deployment; the prose
    docs at developers.symphonyfintech.in were right).
  - `futureSymbol`/`optionsymbol` responses are a list-of-one, not a
    bare object like the docs' examples show.
  - OHLC `dataReponse` is comma-separated pipe-delimited rows. Each
    row's timestamp is IST wall-clock time encoded as a pseudo-epoch
    (reading it with a UTC offset recovers the correct IST clock time
    directly -- no +5:30 conversion needed), stamped at :59 seconds
    (end of minute) not :00 -- see get_candle_at()'s docstring.
  - GetStrikePrice (`resolve_nifty_option_grid`) works live despite
    not being in the reference SDK's route table at all (only in the
    prose docs).

STILL UNVERIFIED / KNOWN GAPS:
  - Interactive API: `/interactive/user/session` returns a real
    structured XTS response (confirming the path), but the
    JAINAM_INTERACTIVE_API_KEY/SECRET in use were rejected with
    "Entered invalid credentials". get_open_nifty_option_positions()
    has never successfully run -- likely needs a separate
    Interactive-scoped key pair from Jainam, distinct from the Market
    Data one. jainam/scripts/dry_run_exit.py works around this by
    never calling it (replays the prior day's signal instead of
    querying real positions).
  - get_option_ltp() / `_quote_ltp` for NSEFO (futures/options)
    instruments returned an empty `listQuotes` when tested after
    market hours on 2026-10-01, even right after explicitly
    subscribing -- while the VIX index quote (NSECM segment) worked
    fine after-hours in the same session. Not yet retested during live
    market hours, so it's unclear whether this is a closed-market
    caching gap or a segment entitlement issue.
  - `compressionValue=60` for 1-minute OHLC candles: the docs list
    both a label ("In1Minute (60)") and bare seconds elsewhere; this
    code sends the bare numeric string "60" -- worked in testing, not
    exhaustively confirmed against every compression value.
"""

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

IST = ZoneInfo("Asia/Kolkata")

NSE_CM_SEGMENT = 1  # equity cash + indices
NSE_FO_SEGMENT = 2  # futures & options


class InstrumentNotFoundError(Exception):
    """Raised when a required instrument can't be resolved. Never guess a symbol."""


class CandleNotFoundError(Exception):
    """Raised when the expected candle isn't present in the OHLC response."""


@dataclass(frozen=True)
class Candle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float


def _fmt_expiry(d: date) -> str:
    """XTS instrument-lookup endpoints take expiry as DDMonYYYY, e.g. 30Jan2025."""
    return d.strftime("%d%b%Y")


def _fmt_ohlc_time(dt: datetime) -> str:
    """OHLC start/end time format per docs, e.g. 'Jan 27 2025 090000'."""
    return dt.strftime("%b %d %Y %H%M%S")


class XTSDataClient:
    def __init__(self, base_url: str, market_token: str, interactive_token: str | None):
        self.base_url = base_url.rstrip("/")
        self.market_token = market_token
        self.interactive_token = interactive_token
        self._interactive_error: str | None = None
        self._session = requests.Session()
        self._index_list_cache: dict[int, dict[str, int]] = {}

    @classmethod
    def from_env(cls, env_path: str | None = None) -> "XTSDataClient":
        """
        Logs into Market Data (required -- entry signal needs it) and,
        if Interactive credentials are present, Interactive too (needed
        only for get_open_nifty_option_positions). A failed or missing
        Interactive login does NOT raise here -- it's deferred until a
        method that actually needs it is called, so market-data-only
        usage (the entry dry run) isn't blocked by it.
        """
        load_dotenv(env_path)
        base_url = os.environ.get("JAINAM_BASE_URL")
        market_api_key = os.environ.get("JAINAM_MARKET_API_KEY")
        market_api_secret = os.environ.get("JAINAM_MARKET_API_SECRET")
        interactive_api_key = os.environ.get("JAINAM_INTERACTIVE_API_KEY")
        interactive_api_secret = os.environ.get("JAINAM_INTERACTIVE_API_SECRET")
        source = os.environ.get("JAINAM_SOURCE", "WEBAPI")

        required = {
            "JAINAM_BASE_URL": base_url,
            "JAINAM_MARKET_API_KEY": market_api_key,
            "JAINAM_MARKET_API_SECRET": market_api_secret,
        }
        missing = [name for name, val in required.items() if not val]
        if missing:
            raise RuntimeError(f"Missing in .env: {', '.join(missing)}")

        session = requests.Session()
        market_token = _login(
            session, base_url, "/apibinarymarketdata/auth/login", market_api_key, market_api_secret, source
        )

        interactive_token = None
        interactive_error = None
        if interactive_api_key and interactive_api_secret:
            try:
                interactive_token = _login(
                    session, base_url, "/interactive/user/session", interactive_api_key, interactive_api_secret, source
                )
            except Exception as exc:  # noqa: BLE001 -- deliberately deferred, see docstring
                interactive_error = str(exc)
        else:
            interactive_error = "JAINAM_INTERACTIVE_API_KEY/SECRET not set in .env"

        client = cls(base_url=base_url, market_token=market_token, interactive_token=interactive_token)
        client._session = session
        client._interactive_error = interactive_error
        return client

    # --- low-level request helpers ----------------------------------------

    def _market_get(self, path: str, params: dict) -> dict:
        return _request(self._session, "GET", self.base_url, path, self.market_token, params=params)

    def _market_post(self, path: str, body: dict) -> dict:
        return _request(self._session, "POST", self.base_url, path, self.market_token, json_body=body)

    def _interactive_get(self, path: str, params: dict) -> dict:
        return _request(self._session, "GET", self.base_url, path, self.interactive_token, params=params)

    # --- VIX -----------------------------------------------------------

    def _index_list(self, exchange_segment: int) -> dict[str, int]:
        """Name -> exchangeInstrumentID for all indices in a segment, e.g. 'INDIA VIX' -> 26002."""
        if exchange_segment not in self._index_list_cache:
            data = self._market_get("/apibinarymarketdata/instruments/indexlist", {"exchangeSegment": exchange_segment})
            mapping = {}
            for entry in data["result"]["indexList"]:
                name, _, instrument_id = entry.rpartition("_")
                mapping[name] = int(instrument_id)
            self._index_list_cache[exchange_segment] = mapping
        return self._index_list_cache[exchange_segment]

    def _quote_ltp(self, exchange_segment: int, exchange_instrument_id: int) -> float:
        data = self._market_post(
            "/apibinarymarketdata/instruments/quotes",
            {
                "instruments": [
                    {"exchangeSegment": exchange_segment, "exchangeInstrumentID": exchange_instrument_id}
                ],
                "xtsMessageCode": 1501,  # TouchLineEvent -- includes LastTradedPrice
                "publishFormat": "JSON",
            },
        )
        quotes = data["result"]["listQuotes"]
        if not quotes:
            raise InstrumentNotFoundError(
                f"No quote returned for segment={exchange_segment} instrumentID={exchange_instrument_id}"
            )
        import json as _json

        quote = quotes[0]
        # Docs show this field double-JSON-encoded (a JSON string inside the JSON
        # response) -- handle both that and a plain dict, since it's unverified.
        if isinstance(quote, str):
            quote = _json.loads(quote)
        return float(quote["LastTradedPrice"])

    def get_india_vix(self) -> float:
        indices = self._index_list(NSE_CM_SEGMENT)
        if "INDIA VIX" not in indices:
            raise InstrumentNotFoundError("INDIA VIX not found in NSECM index list")
        return self._quote_ltp(NSE_CM_SEGMENT, indices["INDIA VIX"])

    def get_historical_vix_at_1515(self, target_date: date) -> float:
        """Approximate 'VIX at 15:15' for a past date via the 15:14 candle close, for replay."""
        indices = self._index_list(NSE_CM_SEGMENT)
        if "INDIA VIX" not in indices:
            raise InstrumentNotFoundError("INDIA VIX not found in NSECM index list")
        return self.get_candle_at(NSE_CM_SEGMENT, indices["INDIA VIX"], target_date, time(15, 14)).close

    def get_option_ltp(self, exchange_instrument_id: int) -> float:
        """Live last-traded price for a resolved NFO option instrument."""
        return self._quote_ltp(NSE_FO_SEGMENT, exchange_instrument_id)

    # --- instrument resolution --------------------------------------------

    def get_nifty_fut_instrument(self, as_of: date) -> dict:
        """Resolve the current (nearest-unexpired) NIFTY futures contract as of the given date."""
        data = self._market_get(
            "/apibinarymarketdata/instruments/instrument/expiryDate",
            {"exchangeSegment": NSE_FO_SEGMENT, "series": "FUTIDX", "symbol": "NIFTY"},
        )
        expiries = [datetime.fromisoformat(e).date() for e in data["result"]]
        candidates = sorted(e for e in expiries if e >= as_of)
        if not candidates:
            raise InstrumentNotFoundError(f"No NIFTY future found with expiry >= {as_of}")
        nearest_expiry = candidates[0]

        data = self._market_get(
            "/apibinarymarketdata/instruments/instrument/futureSymbol",
            {
                "exchangeSegment": NSE_FO_SEGMENT,
                "series": "FUTIDX",
                "symbol": "NIFTY",
                "expiryDate": _fmt_expiry(nearest_expiry),
            },
        )
        results = data["result"]
        if not results:
            raise InstrumentNotFoundError(f"No NIFTY future found for expiry {nearest_expiry}")
        result = results[0]
        return {
            "tradingsymbol": result["Description"],
            "instrument_token": result["ExchangeInstrumentID"],
            "expiry": nearest_expiry,
        }

    def resolve_nifty_option_grid(self, expiry: date) -> tuple[float, int]:
        """
        Return (strike_interval, lot_size) for NIFTY options at the given expiry.

        Uses the strikePrice endpoint, which appears in Symphony's prose docs
        but is NOT implemented in their reference Python SDK's route table --
        unlike every other route in this file, this path could not be
        cross-checked against working code. Verify it resolves before relying
        on it live.
        """
        data = self._market_get(
            "/apibinarymarketdata/instruments/instrument/strikePrice",
            {
                "exchangeSegment": NSE_FO_SEGMENT,
                "series": "OPTIDX",
                "symbol": "NIFTY",
                "expiryDate": _fmt_expiry(expiry),
                "optionType": "CE",
            },
        )
        strikes = sorted({float(s) for s in data["result"]})
        if len(strikes) < 2:
            raise InstrumentNotFoundError(
                f"Fewer than 2 strikes listed for NIFTY expiry {expiry}; cannot derive interval"
            )
        diffs = [round(b - a, 2) for a, b in zip(strikes, strikes[1:])]
        strike_interval = min(diffs)

        # Lot size isn't part of the strike list -- pull it off any one resolved
        # option instrument for this expiry (lot size is uniform per underlying/expiry).
        sample = self.resolve_option_instrument(strikes[0], "CE", expiry)
        lot_size = sample["lot_size"]
        return strike_interval, lot_size

    def resolve_option_instrument(self, strike: float, option_type: str, expiry: date) -> dict:
        if option_type not in ("CE", "PE"):
            raise ValueError(f"option_type must be CE or PE, got {option_type!r}")
        data = self._market_get(
            "/apibinarymarketdata/instruments/instrument/optionsymbol",
            {
                "exchangeSegment": NSE_FO_SEGMENT,
                "series": "OPTIDX",
                "symbol": "NIFTY",
                "expiryDate": _fmt_expiry(expiry),
                "optionType": option_type,
                "strikePrice": strike,
            },
        )
        results = data.get("result")
        if not results:
            raise InstrumentNotFoundError(
                f"No NIFTY {option_type} found for strike={strike} expiry={expiry}"
            )
        result = results[0]
        return {
            "tradingsymbol": result["Description"],
            "instrument_token": result["ExchangeInstrumentID"],
            "lot_size": result["LotSize"],
        }

    # --- candles ---------------------------------------------------------

    def get_candle_at(self, exchange_segment: int, exchange_instrument_id: int, target_date: date, target_time: time) -> Candle:
        """
        Fetch the 1-minute candle covering target_date + target_time.
        Raises CandleNotFoundError if the OHLC response doesn't contain
        that minute.

        VERIFIED live on 2026-10-01: `dataReponse` is a comma-separated
        list of pipe-delimited rows (timestamp|O|H|L|C|volume|OI|). The
        timestamp is NOT a true Unix/UTC epoch -- it's the IST
        wall-clock time encoded as if it were a UTC epoch (i.e. reading
        it with a UTC offset recovers the correct IST clock time
        directly, no +5:30 conversion needed). Each row is also stamped
        at :59 seconds (end of its minute), not :00 -- so matching is
        done by (date, hour, minute), ignoring seconds.
        """
        start_dt = datetime.combine(target_date, time(9, 0))
        end_dt = datetime.combine(target_date, time(15, 30))
        data = self._market_get(
            "/apibinarymarketdata/instruments/ohlc",
            {
                "exchangeSegment": exchange_segment,
                "exchangeInstrumentID": exchange_instrument_id,
                "startTime": _fmt_ohlc_time(start_dt),
                "endTime": _fmt_ohlc_time(end_dt),
                "compressionValue": "60",
            },
        )
        raw = data["result"]["dataReponse"]
        for row in raw.split(","):
            fields = row.split("|")
            if len(fields) < 5 or not fields[0]:
                continue
            row_dt = datetime.fromtimestamp(int(fields[0]), tz=timezone.utc).replace(tzinfo=IST)
            if (row_dt.date(), row_dt.hour, row_dt.minute) == (target_date, target_time.hour, target_time.minute):
                return Candle(
                    timestamp=row_dt,
                    open=float(fields[1]),
                    high=float(fields[2]),
                    low=float(fields[3]),
                    close=float(fields[4]),
                )
        raise CandleNotFoundError(
            f"No candle found for {target_date} {target_time} for instrument {exchange_instrument_id}"
        )

    def get_nifty_fut_open_0915(self, target_date: date, exchange_instrument_id: int) -> float:
        return self.get_candle_at(NSE_FO_SEGMENT, exchange_instrument_id, target_date, time(9, 15)).open

    def get_nifty_fut_1514_close(self, target_date: date, exchange_instrument_id: int) -> float:
        return self.get_candle_at(NSE_FO_SEGMENT, exchange_instrument_id, target_date, time(15, 14)).close

    # --- spot (for ATM strike selection) ----------------------------------

    def get_nifty_spot_1514_close(self, target_date: date) -> float:
        indices = self._index_list(NSE_CM_SEGMENT)
        if "NIFTY 50" not in indices:
            raise InstrumentNotFoundError("NIFTY 50 not found in NSECM index list")
        return self.get_candle_at(
            NSE_CM_SEGMENT, indices["NIFTY 50"], target_date, time(15, 14)
        ).close

    # --- positions ---------------------------------------------------------

    def get_open_nifty_option_positions(self) -> list[dict]:
        """Live net NIFTY option positions with nonzero quantity. Read-only."""
        if not self.interactive_token:
            raise RuntimeError(
                f"Interactive API session not available: {self._interactive_error}"
            )
        data = self._interactive_get("/interactive/portfolio/positions", {"dayOrNet": "NetWise"})
        rows = data.get("result") or []
        return [
            row
            for row in rows
            if row.get("TradingSymbol", "").startswith("NIFTY")
            and row.get("ExchangeSegment") == "NSEFO"
            and row.get("Quantity", 0) != 0
        ]


def _login(session: requests.Session, base_url: str, path: str, app_key: str, secret_key: str, source: str) -> str:
    data = _request(
        session,
        "POST",
        base_url,
        path,
        token=None,
        json_body={"appKey": app_key, "secretKey": secret_key, "source": source},
    )
    try:
        return data["result"]["token"]
    except KeyError as exc:
        raise RuntimeError(f"Login to {path} did not return a token: {data}") from exc


def _request(
    session: requests.Session,
    method: str,
    base_url: str,
    path: str,
    token: str | None,
    params: dict | None = None,
    json_body: dict | None = None,
) -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = token
    response = session.request(
        method, base_url.rstrip("/") + path, headers=headers, params=params, json=json_body, timeout=10
    )
    response.raise_for_status()
    data = response.json()
    if data.get("type") == "error":
        raise RuntimeError(f"XTS API error on {path}: {data.get('description')}")
    return data
