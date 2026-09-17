"""
Read-only Jainam (XTS-based) market-data + positions layer.

Jainam white-labels Symphony Fintech's XTS Connect API. This talks to
the documented REST endpoints directly with `requests` -- it does not
vendor Symphony's own Python SDK (github.com/symphonyfintech/xts-pythonclient-api-sdk),
since that repo carries no open-source license despite being public.
The route paths and request/response shapes below were cross-checked
against that SDK's source (the authoritative route table) rather than
taken solely from the prose docs at developers.symphonyfintech.in,
where the two disagreed (e.g. the docs page shows a login path of
`/1interactive/user/session`; the SDK's route table -- what real
broker integrations actually run against -- uses `/interactive/user/session`).

Deliberately no order placement/status/cancel here yet -- this is the
dry-run/data-fetch phase only, mirroring broker/kite_client.py. All
methods either return real data or raise clearly; nothing here guesses
a symbol or silently falls back.

CONFIRM BEFORE LIVE -- built from API documentation only, no live
Jainam session was available to test against, unlike kite_client.py
(which was verified against a real Kite session). Before trusting this
for real dry runs:
  - JAINAM_BASE_URL must be Jainam's own production host (obtained from
    their API dashboard once you register) -- developers.symphonyfintech.in
    is Symphony's own dev sandbox, not Jainam's live endpoint.
  - OHLC candle parsing (`_parse_ohlc_candles`): the docs only show a
    single-candle example response (`dataReponse` as one pipe-delimited
    string). The separator between multiple candles in a multi-candle
    response (comma vs newline) is not documented -- this code assumes
    comma-separated rows. Verify against a real response.
  - OHLC candle timestamp: assumed to be a true Unix epoch (UTC)
    second, converted to IST for comparison -- same unverified
    assumption flagged in kite_client.py's IST_CANDLE_TZ_NOTE, must be
    checked against a known historical value before trusting it live.
  - `compressionValue=60` for 1-minute candles: the docs list both a
    label ("In1Minute (60)") and bare seconds elsewhere; this code
    sends the bare numeric string "60".
"""

import os
from dataclasses import dataclass
from datetime import date, datetime, time
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
    def __init__(self, base_url: str, market_token: str, interactive_token: str):
        self.base_url = base_url.rstrip("/")
        self.market_token = market_token
        self.interactive_token = interactive_token
        self._session = requests.Session()
        self._index_list_cache: dict[int, dict[str, int]] = {}

    @classmethod
    def from_env(cls, env_path: str | None = None) -> "XTSDataClient":
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
            "JAINAM_INTERACTIVE_API_KEY": interactive_api_key,
            "JAINAM_INTERACTIVE_API_SECRET": interactive_api_secret,
        }
        missing = [name for name, val in required.items() if not val]
        if missing:
            raise RuntimeError(f"Missing in .env: {', '.join(missing)}")

        session = requests.Session()
        market_token = _login(
            session, base_url, "/apimarketdata/auth/login", market_api_key, market_api_secret, source
        )
        interactive_token = _login(
            session, base_url, "/interactive/user/session", interactive_api_key, interactive_api_secret, source
        )
        client = cls(base_url=base_url, market_token=market_token, interactive_token=interactive_token)
        client._session = session
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
            data = self._market_get("/apimarketdata/instruments/indexlist", {"exchangeSegment": exchange_segment})
            mapping = {}
            for entry in data["result"]["indexList"]:
                name, _, instrument_id = entry.rpartition("_")
                mapping[name] = int(instrument_id)
            self._index_list_cache[exchange_segment] = mapping
        return self._index_list_cache[exchange_segment]

    def _quote_ltp(self, exchange_segment: int, exchange_instrument_id: int) -> float:
        data = self._market_post(
            "/apimarketdata/instruments/quotes",
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

    # --- instrument resolution --------------------------------------------

    def get_nifty_fut_instrument(self, as_of: date) -> dict:
        """Resolve the current (nearest-unexpired) NIFTY futures contract as of the given date."""
        data = self._market_get(
            "/apimarketdata/instruments/instrument/expiryDate",
            {"exchangeSegment": NSE_FO_SEGMENT, "series": "FUTIDX", "symbol": "NIFTY"},
        )
        expiries = [datetime.fromisoformat(e).date() for e in data["result"]]
        candidates = sorted(e for e in expiries if e >= as_of)
        if not candidates:
            raise InstrumentNotFoundError(f"No NIFTY future found with expiry >= {as_of}")
        nearest_expiry = candidates[0]

        data = self._market_get(
            "/apimarketdata/instruments/instrument/futureSymbol",
            {
                "exchangeSegment": NSE_FO_SEGMENT,
                "series": "FUTIDX",
                "symbol": "NIFTY",
                "expiryDate": _fmt_expiry(nearest_expiry),
            },
        )
        result = data["result"]
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
            "/apimarketdata/instruments/instrument/strikePrice",
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
            "/apimarketdata/instruments/instrument/optionsymbol",
            {
                "exchangeSegment": NSE_FO_SEGMENT,
                "series": "OPTIDX",
                "symbol": "NIFTY",
                "expiryDate": _fmt_expiry(expiry),
                "optionType": option_type,
                "strikePrice": strike,
            },
        )
        result = data.get("result")
        if not result:
            raise InstrumentNotFoundError(
                f"No NIFTY {option_type} found for strike={strike} expiry={expiry}"
            )
        return {
            "tradingsymbol": result["Description"],
            "instrument_token": result["ExchangeInstrumentID"],
            "lot_size": result["LotSize"],
        }

    # --- candles ---------------------------------------------------------

    def get_candle_at(self, exchange_segment: int, exchange_instrument_id: int, target_date: date, target_time: time) -> Candle:
        """
        Fetch the 1-minute candle whose start timestamp is exactly
        target_date + target_time. Raises CandleNotFoundError if the OHLC
        response doesn't contain that exact minute.
        """
        start_dt = datetime.combine(target_date, time(9, 0))
        end_dt = datetime.combine(target_date, time(15, 30))
        data = self._market_get(
            "/apimarketdata/instruments/ohlc",
            {
                "exchangeSegment": exchange_segment,
                "exchangeInstrumentID": exchange_instrument_id,
                "startTime": _fmt_ohlc_time(start_dt),
                "endTime": _fmt_ohlc_time(end_dt),
                "compressionValue": "60",
            },
        )
        raw = data["result"]["dataReponse"]
        target_dt = datetime.combine(target_date, target_time, tzinfo=IST)
        for row in raw.split(","):
            fields = row.split("|")
            if len(fields) < 5 or not fields[0]:
                continue
            row_dt = datetime.fromtimestamp(int(fields[0]), tz=IST)
            if row_dt == target_dt:
                return Candle(
                    timestamp=row_dt,
                    open=float(fields[1]),
                    high=float(fields[2]),
                    low=float(fields[3]),
                    close=float(fields[4]),
                )
        raise CandleNotFoundError(
            f"No candle found starting at {target_dt} for instrument {exchange_instrument_id}"
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
