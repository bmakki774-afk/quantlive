"""
Twelve Data candle fetcher for XAU/USD.

Fetches OHLCV data for all required timeframes and returns
pandas DataFrames ready for the ICT analysis engine.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests

import config
from db.store import upsert_candles

log = logging.getLogger(__name__)

BASE_URL = "https://api.twelvedata.com"
RATE_LIMIT_SLEEP = 12  # seconds between requests (free tier: 8 req/min)


class TwelveDataFetcher:
    """Fetch and cache OHLCV candles from Twelve Data."""

    def __init__(self, api_key: str = config.TWELVE_DATA_API_KEY):
        self.api_key = api_key
        if not api_key:
            raise ValueError("TWELVE_DATA_API_KEY is not set. Add it to your .env file.")

    # ââ Public API ââââââââââââââââââââââââââââââââââââââââââââââ

    def fetch_all_timeframes(
        self,
        symbol: str = config.SYMBOL,
        timeframes: list[str] = None,
        lookback: int = config.CANDLE_LOOKBACK,
        persist: bool = True,
    ) -> dict[str, pd.DataFrame]:
        """
        Fetch candles for all configured timeframes.

        Returns dict keyed by timeframe string:
          { "15min": DataFrame, "1h": DataFrame, "4h": DataFrame, "1day": DataFrame }
        """
        if timeframes is None:
            timeframes = config.TIMEFRAMES

        result: dict[str, pd.DataFrame] = {}

        for i, tf in enumerate(timeframes):
            try:
                df = self.fetch(symbol=symbol, timeframe=tf, lookback=lookback)
                result[tf] = df
                if persist:
                    self._persist(symbol, tf, df)
                log.info(f"Fetched {len(df)} candles [{symbol} {tf}]")
            except Exception as exc:
                log.error(f"Failed to fetch {symbol} {tf}: {exc}")
                result[tf] = pd.DataFrame()

            # Respect rate limit between requests (skip sleep on last)
            if i < len(timeframes) - 1:
                time.sleep(RATE_LIMIT_SLEEP)

        return result

    def fetch(
        self,
        symbol: str = config.SYMBOL,
        timeframe: str = "1h",
        lookback: int = config.CANDLE_LOOKBACK,
    ) -> pd.DataFrame:
        """Fetch a single timeframe. Returns cleaned DataFrame."""
        params = {
            "symbol": symbol,
            "interval": timeframe,
            "outputsize": lookback,
            "format": "JSON",
            "order": "ASC",         # oldest first
            "apikey": self.api_key,
        }

        resp = requests.get(f"{BASE_URL}/time_series", params=params, timeout=30)
        resp.raise_for_status()

        data = resp.json()

        if data.get("status") == "error":
            raise RuntimeError(f"Twelve Data error: {data.get('message', data)}")

        values = data.get("values", [])
        if not values:
            log.warning(f"No candle data returned for {symbol} {timeframe}.")
            return pd.DataFrame()

        df = pd.DataFrame(values)
        df = self._clean(df)
        return df

    # ââ Helpers âââââââââââââââââââââââââââââââââââââââââââââââââ

    def _clean(self, df: pd.DataFrame) -> pd.DataFrame:
        """Parse types and ensure consistent column names."""
        df = df.copy()
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        if "volume" in df.columns:
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
        else:
            df["volume"] = 0.0
        df.sort_values("datetime", inplace=True)
        df.reset_index(drop=True, inplace=True)
        df.dropna(subset=["open", "high", "low", "close"], inplace=True)
        return df

    def _persist(self, symbol: str, timeframe: str, df: pd.DataFrame):
        """Write candles to the database."""
        rows = df.to_dict(orient="records")
        upsert_candles(symbol, timeframe, rows)

    def get_current_price(self, symbol: str = config.SYMBOL) -> Optional[float]:
        """Fetch the latest price via the /price endpoint."""
        try:
            resp = requests.get(
                f"{BASE_URL}/price",
                params={"symbol": symbol, "apikey": self.api_key},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            return float(data.get("price", 0))
        except Exception as exc:
            log.error(f"Could not fetch current price: {exc}")
            return None

    def get_current_session(self) -> str:
        """Return current trading session based on UTC hour."""
        hour = datetime.now(timezone.utc).hour
        if config.LONDON_KZ_START <= hour < config.LONDON_KZ_END:
            return "London"
        elif config.NEW_YORK_KZ_START <= hour < config.NEW_YORK_KZ_END:
            return "New York"
        elif 0 <= hour < 3:
            return "Asian"
        else:
            return "Off-Hours"
