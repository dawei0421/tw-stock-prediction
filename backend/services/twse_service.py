"""TWSE API service for institutional trading data and margin trading data."""

import asyncio
from datetime import datetime

import httpx
from loguru import logger

from core.cache import twse_cache, intraday_cache


class TWSEService:
    """Fetches institutional and margin data from TWSE open APIs."""

    BASE_URL = "https://www.twse.com.tw"
    MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
    TIMEOUT = 10.0

    def __init__(self):
        self._headers = {
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        }

    async def get_intraday_quote(self, stock_id: str, market: str = "TWSE") -> dict | None:
        """Fetch real-time intraday quote from TWSE MIS API (盤中即時報價).

        Only meaningful during market hours (Mon-Fri 09:00-13:30 Taipei time).
        Returns None if data is unavailable or market is not trading.
        """
        cache_key = f"intraday:{stock_id}"
        cached = intraday_cache.get(cache_key)
        if cached is not None:
            return cached

        ex = "otc" if market == "TPEX" else "tse"
        ex_ch = f"{ex}_{stock_id}.tw"
        url = f"{self.MIS_URL}?ex_ch={ex_ch}&json=1&delay=0"
        headers = {**self._headers, "Referer": "https://mis.twse.com.tw/stock/fibest.html"}

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            items = data.get("msgArray", [])
            if not items:
                return None

            item = items[0]

            def _f(key: str) -> float | None:
                v = item.get(key, "-")
                if v in ("-", "", None):
                    return None
                try:
                    return float(v)
                except (ValueError, TypeError):
                    return None

            current = _f("z")   # 最新成交價
            prev_close = _f("y")  # 昨收
            if current is None:
                current = prev_close  # 開盤前或無成交時用昨收

            if current is None:
                return None

            result = {
                "current_price": round(current, 2),
                "open": _f("o"),
                "high": _f("h"),
                "low": _f("l"),
                "prev_close": round(prev_close, 2) if prev_close else None,
                "volume": int(str(item.get("v", "0")).replace(",", "") or 0),
                "trade_time": item.get("t", ""),
            }
            intraday_cache[cache_key] = result
            return result

        except Exception as e:
            logger.warning(f"TWSE MIS intraday fetch failed for {stock_id}: {e}")
            return None

    async def get_institutional_data(self, stock_id: str) -> dict:
        """
        Get institutional buy/sell data for a stock from TWSE T86 API.

        Returns:
            dict with keys: foreign_buy, foreign_sell, foreign_net,
                           trust_buy, trust_sell, trust_net,
                           dealer_buy, dealer_sell, dealer_net,
                           total_net
        """
        cache_key = f"institutional:{stock_id}"
        cached = twse_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            all_data = await self._fetch_t86_data()
            if not all_data:
                return self._empty_institutional()

            result = all_data.get(stock_id, self._empty_institutional())
            twse_cache[cache_key] = result
            return result

        except Exception as e:
            logger.warning(f"Failed to get institutional data for {stock_id}: {e}")
            return self._empty_institutional()

    async def get_margin_data(self, stock_id: str) -> dict:
        """
        Get margin trading data (融資融券) from TWSE MI_MARGN API.

        Returns:
            dict with keys: margin_buy, margin_sell, margin_net,
                           short_buy, short_sell, short_net
        """
        cache_key = f"margin:{stock_id}"
        cached = twse_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            today = datetime.now().strftime("%Y%m%d")
            url = f"{self.BASE_URL}/exchangeReport/MI_MARGN?response=json&date={today}&selectType=ALL"

            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                resp = await client.get(url, headers=self._headers)
                resp.raise_for_status()
                data = resp.json()

            # Parse margin data
            rows = data.get("tables", [{}])
            margin_table = None
            for table in rows:
                if "data" in table:
                    margin_table = table["data"]
                    break

            if not margin_table:
                return self._empty_margin()

            for row in margin_table:
                if len(row) < 13:
                    continue
                code = str(row[0]).strip()
                if code == stock_id:
                    result = {
                        "margin_buy": self._safe_int(row[2]),
                        "margin_sell": self._safe_int(row[3]),
                        "margin_net": self._safe_int(row[2]) - self._safe_int(row[3]),
                        "short_buy": self._safe_int(row[8]),
                        "short_sell": self._safe_int(row[9]),
                        "short_net": self._safe_int(row[9]) - self._safe_int(row[8]),
                    }
                    twse_cache[cache_key] = result
                    return result

            return self._empty_margin()

        except Exception as e:
            logger.warning(f"Failed to get margin data for {stock_id}: {e}")
            return self._empty_margin()

    async def _fetch_t86_data(self) -> dict:
        """Fetch and parse T86 (institutional trading) data. Cached per session."""
        cache_key = "t86_all"
        cached = twse_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            today = datetime.now().strftime("%Y%m%d")
            url = f"{self.BASE_URL}/fund/T86?response=json&date={today}&selectType=ALLBUT0999"

            async with httpx.AsyncClient(timeout=self.TIMEOUT) as client:
                resp = await client.get(url, headers=self._headers)
                resp.raise_for_status()
                data = resp.json()

            rows = data.get("data", [])
            result = {}

            for row in rows:
                if len(row) < 19:
                    continue
                code = str(row[0]).strip()
                result[code] = {
                    "foreign_buy": self._safe_int(row[2]),
                    "foreign_sell": self._safe_int(row[3]),
                    "foreign_net": self._safe_int(row[4]),
                    "trust_buy": self._safe_int(row[8]),
                    "trust_sell": self._safe_int(row[9]),
                    "trust_net": self._safe_int(row[10]),
                    "dealer_buy": self._safe_int(row[12]),
                    "dealer_sell": self._safe_int(row[13]),
                    "dealer_net": self._safe_int(row[14]),
                    "total_net": self._safe_int(row[18]),
                }

            twse_cache[cache_key] = result
            return result

        except Exception as e:
            logger.warning(f"Failed to fetch T86 data: {e}")
            return {}

    @staticmethod
    def _safe_int(val) -> int:
        """Parse a value to int, stripping commas and whitespace."""
        try:
            return int(str(val).replace(",", "").strip())
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _empty_institutional() -> dict:
        return {
            "foreign_buy": 0, "foreign_sell": 0, "foreign_net": 0,
            "trust_buy": 0, "trust_sell": 0, "trust_net": 0,
            "dealer_buy": 0, "dealer_sell": 0, "dealer_net": 0,
            "total_net": 0,
        }

    @staticmethod
    def _empty_margin() -> dict:
        return {
            "margin_buy": 0, "margin_sell": 0, "margin_net": 0,
            "short_buy": 0, "short_sell": 0, "short_net": 0,
        }
