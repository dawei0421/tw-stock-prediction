"""Quote service: real market data via yfinance for Taiwan stocks."""

import asyncio
import dataclasses
import re
from datetime import datetime, time as dtime
from typing import Optional
from zoneinfo import ZoneInfo

import yfinance as yf
from loguru import logger

from core.cache import quote_cache, stock_info_cache, history_cache, signal_cache, rate_limit_cache, raw_df_cache
from services.signal_engine import MarketData
from services.twse_service import TWSEService

_TAIPEI_TZ = ZoneInfo("Asia/Taipei")


def is_market_open() -> bool:
    """Return True if Taiwan stock market is currently open (Mon-Fri 09:00-13:30 Taipei time)."""
    now = datetime.now(tz=_TAIPEI_TZ)
    if now.weekday() >= 5:
        return False
    return dtime(9, 0) <= now.time() <= dtime(13, 30)


# Common Taiwan stocks and ETFs for search suggestions.
# Unknown codes are still queryable via direct lookup through yfinance.
KNOWN_STOCKS: dict[str, dict] = {
    # 權值股
    "2330": {"name": "台積電", "market": "TWSE"},
    "2317": {"name": "鴻海", "market": "TWSE"},
    "2454": {"name": "聯發科", "market": "TWSE"},
    "2308": {"name": "台達電", "market": "TWSE"},
    "2881": {"name": "富邦金", "market": "TWSE"},
    "2882": {"name": "國泰金", "market": "TWSE"},
    "2891": {"name": "中信金", "market": "TWSE"},
    "2303": {"name": "聯電", "market": "TWSE"},
    "3711": {"name": "日月光投控", "market": "TWSE"},
    "2412": {"name": "中華電", "market": "TWSE"},
    "1301": {"name": "台塑", "market": "TWSE"},
    "1303": {"name": "南亞", "market": "TWSE"},
    "2886": {"name": "兆豐金", "market": "TWSE"},
    "2002": {"name": "中鋼", "market": "TWSE"},
    "3008": {"name": "大立光", "market": "TWSE"},
    "2382": {"name": "廣達", "market": "TWSE"},
    "2357": {"name": "華碩", "market": "TWSE"},
    "2379": {"name": "瑞昱", "market": "TWSE"},
    "2603": {"name": "長榮", "market": "TWSE"},
    "2615": {"name": "萬海", "market": "TWSE"},
    "2609": {"name": "陽明", "market": "TWSE"},
    "2887": {"name": "台新金", "market": "TWSE"},
    "2892": {"name": "第一金", "market": "TWSE"},
    "5880": {"name": "合庫金", "market": "TWSE"},
    "2884": {"name": "玉山金", "market": "TWSE"},
    "2885": {"name": "元大金", "market": "TWSE"},
    "6505": {"name": "台塑化", "market": "TWSE"},
    "6488": {"name": "環球晶", "market": "TPEX"},
    "5274": {"name": "信驊", "market": "TPEX"},
    "6415": {"name": "矽力-KY", "market": "TPEX"},
    "3293": {"name": "鈊象", "market": "TPEX"},
    "4966": {"name": "譜瑞-KY", "market": "TPEX"},
    # 熱門 ETF
    "0050": {"name": "元大台灣50", "market": "TWSE"},
    "0056": {"name": "元大高股息", "market": "TWSE"},
    "006208": {"name": "富邦台50", "market": "TWSE"},
    "00878": {"name": "國泰永續高股息", "market": "TWSE"},
    "00919": {"name": "群益台灣精選高息", "market": "TWSE"},
    "00929": {"name": "復華台灣科技優息", "market": "TWSE"},
    "00713": {"name": "元大台灣高息低波", "market": "TWSE"},
    "00900": {"name": "富邦特選高股息30", "market": "TWSE"},
    "00881": {"name": "國泰台灣5G+", "market": "TWSE"},
    "00892": {"name": "富邦台灣半導體", "market": "TWSE"},
    "00940": {"name": "元大台灣價值高息", "market": "TWSE"},
    "00679B": {"name": "元大美債20年", "market": "TWSE"},
    "00937B": {"name": "群益ESG投等債20+", "market": "TWSE"},
    "00687B": {"name": "國泰20年美債", "market": "TWSE"},
    "00757": {"name": "統一FANG+", "market": "TWSE"},
    "00646": {"name": "元大S&P500", "market": "TWSE"},
    "00662": {"name": "富邦NASDAQ", "market": "TWSE"},
}


# Taiwan stock code pattern:
#   - 4 digits: regular stocks (2330, 1101)
#   - 4 digits + B: bond ETFs (00679B, 00937B)
#   - 5-6 digits starting with 00: ETFs (0050, 00878, 006208)
TAIWAN_CODE_PATTERN = re.compile(r"^(\d{4,6}[A-Z]?)$")


def _is_valid_taiwan_code(stock_id: str) -> bool:
    """Check if stock_id matches Taiwan stock code format."""
    return bool(TAIWAN_CODE_PATTERN.match(stock_id))


def _get_ticker_symbol(stock_id: str) -> str:
    """
    Get yfinance ticker symbol for a Taiwan stock.

    Checks KNOWN_STOCKS first, then the stock_info_cache (which is populated
    on successful lookup), then defaults to .TW (covers TWSE stocks and all
    listed ETFs).
    """
    info = KNOWN_STOCKS.get(stock_id)
    if info is None:
        info = stock_info_cache.get(f"info:{stock_id}", {})
    suffix = ".TWO" if info.get("market") == "TPEX" else ".TW"
    return f"{stock_id}{suffix}"


def _fetch_ticker_info(stock_id: str) -> dict:
    """
    Fetch ticker metadata from yfinance and cache it.
    Tries .TW first, falls back to .TWO if no longName is returned.
    Returns {} if completely unavailable.
    """
    cache_key = f"info:{stock_id}"
    if cache_key in stock_info_cache:
        return stock_info_cache[cache_key]

    def _try(ticker_symbol: str) -> dict:
        try:
            t = yf.Ticker(ticker_symbol)
            raw = t.info or {}
            name = raw.get("longName") or raw.get("shortName") or ""
            # Strip common suffixes like " Co., Ltd." to keep UI compact
            name = re.sub(r"[ ,.]*(Co|Corp|Inc|Ltd|Limited)\.?.*$", "", name).strip()
            return {
                "name": name,
                "market": "TPEX" if ticker_symbol.endswith(".TWO") else "TWSE",
                "quote_type": raw.get("quoteType", ""),
            }
        except Exception as e:
            logger.debug(f"yfinance Ticker({ticker_symbol}).info failed: {e}")
            return {}

    # Try primary market first
    primary = _get_ticker_symbol(stock_id)
    info = _try(primary)

    # Fallback to the other market if primary returned no name
    if not info.get("name"):
        fallback = f"{stock_id}.TWO" if primary.endswith(".TW") else f"{stock_id}.TW"
        fallback_info = _try(fallback)
        if fallback_info.get("name"):
            info = fallback_info

    if info.get("name"):
        stock_info_cache[cache_key] = info
        return info
    return {}


def _flatten_columns(df):
    """Handle MultiIndex columns from yfinance and drop NaN rows."""
    if hasattr(df.columns, 'levels'):
        df.columns = df.columns.get_level_values(0)
    # Drop rows where Close is NaN (e.g. today before market close)
    df = df.dropna(subset=["Close"])
    return df


def _download_with_fallback(stock_id: str, period: str, interval: str = "1d"):
    """
    Download OHLCV data with TWSE/TPEX fallback.

    Tries the primary suffix first. If the result is empty AND the stock
    is not in KNOWN_STOCKS, retry with the opposite suffix. This lets us
    transparently query arbitrary Taiwan codes (including TPEX stocks
    and less common ETFs).
    """
    primary = _get_ticker_symbol(stock_id)
    df = yf.download(primary, period=period, interval=interval, progress=False)
    df = _flatten_columns(df)

    if not df.empty or stock_id in KNOWN_STOCKS:
        return df

    # Fallback: try the other market suffix
    fallback = f"{stock_id}.TWO" if primary.endswith(".TW") else f"{stock_id}.TW"
    logger.debug(f"Primary {primary} returned empty, trying fallback {fallback}")
    df = yf.download(fallback, period=period, interval=interval, progress=False)
    df = _flatten_columns(df)

    if not df.empty:
        # Cache the correct market so future calls hit the right suffix
        market = "TPEX" if fallback.endswith(".TWO") else "TWSE"
        cache_key = f"info:{stock_id}"
        existing = stock_info_cache.get(cache_key, {})
        existing["market"] = market
        stock_info_cache[cache_key] = existing

    return df


class QuoteService:
    """Provides real stock quotes and market data via yfinance."""

    def __init__(self):
        self._twse_service = TWSEService()

    def get_stock_name(self, stock_id: str) -> str:
        """Get display name for a stock (KNOWN_STOCKS first, then yfinance info, then fallback)."""
        info = KNOWN_STOCKS.get(stock_id)
        if info:
            return info["name"]
        fetched = _fetch_ticker_info(stock_id)
        if fetched.get("name"):
            return fetched["name"]
        return stock_id

    def get_stock_market(self, stock_id: str) -> str:
        """Get market type (TWSE/TPEX) for a stock."""
        info = KNOWN_STOCKS.get(stock_id)
        if info:
            return info["market"]
        fetched = _fetch_ticker_info(stock_id)
        return fetched.get("market", "TWSE")

    def search_stocks(self, query: str) -> list[dict]:
        """
        Search stocks by code or name.

        Returns:
            1. All KNOWN_STOCKS matching query (code or name contains query)
            2. If query is a valid Taiwan code not in KNOWN_STOCKS, try live lookup
        """
        results = []
        q = query.strip()
        seen: set[str] = set()

        # 1. Match against KNOWN_STOCKS
        for sid, info in KNOWN_STOCKS.items():
            if q in sid or q in info["name"]:
                results.append({
                    "stock_id": sid,
                    "stock_name": info["name"],
                    "market": info["market"],
                })
                seen.add(sid)

        # 2. If query looks like a stock code, try live lookup via yfinance
        if _is_valid_taiwan_code(q) and q not in seen:
            fetched = _fetch_ticker_info(q)
            results.insert(0, {
                "stock_id": q,
                "stock_name": fetched.get("name") or q,
                "market": fetched.get("market", "TWSE"),
            })

        return results[:20]

    async def get_quote(self, stock_id: str) -> dict:
        """Get stock quote. Uses TWSE MIS real-time API during market hours, yfinance otherwise."""
        cache_key = f"quote:{stock_id}"

        # During market hours: use TWSE MIS intraday API (5s TTL handled inside twse_service)
        if is_market_open():
            market = self.get_stock_market(stock_id)
            intraday = await self._twse_service.get_intraday_quote(stock_id, market)
            if intraday and intraday.get("current_price"):
                current_price = intraday["current_price"]
                prev_close = intraday.get("prev_close") or current_price
                open_p = intraday.get("open") or current_price
                high_p = intraday.get("high") or current_price
                low_p = intraday.get("low") or current_price
                change = round(current_price - prev_close, 2)
                change_pct = round((change / prev_close * 100) if prev_close else 0, 2)
                return {
                    "stock_id": stock_id,
                    "stock_name": self.get_stock_name(stock_id),
                    "current_price": current_price,
                    "open": open_p,
                    "high": high_p,
                    "low": low_p,
                    "close": current_price,
                    "volume": intraday.get("volume", 0),
                    "change": change,
                    "change_percent": change_pct,
                    "prev_close": prev_close,
                    "updated_at": datetime.now().isoformat(),
                    "is_intraday": True,
                    "trade_time": intraday.get("trade_time", ""),
                }

        if cache_key in quote_cache:
            return quote_cache[cache_key]

        try:
            df = _download_with_fallback(stock_id, period="5d", interval="1d")
            if df.empty:
                logger.warning(f"No data from yfinance for {stock_id}")
                return self._empty_quote(stock_id)

            # Latest trading day
            latest = df.iloc[-1]
            current_price = round(float(latest["Close"]), 2)
            open_price = round(float(latest["Open"]), 2)
            high_price = round(float(latest["High"]), 2)
            low_price = round(float(latest["Low"]), 2)
            volume = int(latest["Volume"])

            # Previous close for change calculation
            if len(df) >= 2:
                prev_close = round(float(df.iloc[-2]["Close"]), 2)
            else:
                prev_close = open_price

            change = round(current_price - prev_close, 2)
            change_pct = round((change / prev_close * 100) if prev_close else 0, 2)

            quote = {
                "stock_id": stock_id,
                "stock_name": self.get_stock_name(stock_id),
                "current_price": current_price,
                "open": open_price,
                "high": high_price,
                "low": low_price,
                "close": current_price,
                "volume": volume,
                "change": change,
                "change_percent": change_pct,
                "prev_close": prev_close,
                "updated_at": datetime.now().isoformat(),
                "is_intraday": False,
                "trade_time": "",
            }
            quote_cache[cache_key] = quote
            return quote

        except Exception as e:
            logger.error(f"Failed to get quote for {stock_id}: {e}")
            return self._empty_quote(stock_id)

    def _empty_quote(self, stock_id: str) -> dict:
        """Return empty quote when data is unavailable."""
        return {
            "stock_id": stock_id,
            "stock_name": self.get_stock_name(stock_id),
            "current_price": 0,
            "open": 0,
            "high": 0,
            "low": 0,
            "close": 0,
            "volume": 0,
            "change": 0,
            "change_percent": 0,
            "prev_close": 0,
            "updated_at": datetime.now().isoformat(),
        }

    async def get_price(self, stock_id: str) -> float:
        """Get current price for a stock."""
        q = await self.get_quote(stock_id)
        return q["current_price"]

    async def get_market_data(self, stock_id: str) -> MarketData:
        """
        Build MarketData for signal engine.

        Historical daily OHLCV (for RSI/MACD/KD) is cached in raw_df_cache (30min).
        During market hours, current price/OHLCV is overridden with TWSE MIS real-time data.
        """
        cache_key = f"market_data:{stock_id}"

        # Non-market hours: use full signal_cache (60s TTL)
        if not is_market_open() and cache_key in signal_cache:
            return signal_cache[cache_key]

        try:
            # Historical data: cached 30min to avoid repeated yfinance 6mo fetches
            raw_key = f"raw_df:{stock_id}"
            df = raw_df_cache.get(raw_key)
            if df is None:
                df = _download_with_fallback(stock_id, period="6mo", interval="1d")
                if not df.empty:
                    raw_df_cache[raw_key] = df
            if df.empty or len(df) < 5:
                logger.warning(f"Insufficient data for market analysis: {stock_id}")
                return self._empty_market_data(stock_id)

            closes = [round(float(c), 2) for c in df["Close"].tolist()]
            highs = [round(float(h), 2) for h in df["High"].tolist()]
            lows = [round(float(l), 2) for l in df["Low"].tolist()]
            volumes = [int(v) for v in df["Volume"].tolist()]

            current_price = closes[-1]
            prev_close = closes[-2] if len(closes) >= 2 else current_price
            open_price = round(float(df.iloc[-1]["Open"]), 2)
            high_price = highs[-1]
            low_price = lows[-1]
            volume = volumes[-1]

            # Approximate outer/inner volume from price action
            # If close > open, more buying pressure (outer > inner)
            if current_price >= open_price:
                outer_ratio = 0.6
            else:
                outer_ratio = 0.4
            outer_volume = int(volume * outer_ratio)
            inner_volume = volume - outer_volume

            # Approximate bid/ask volumes from recent volume trend
            avg_vol = sum(volumes[-5:]) / 5 if len(volumes) >= 5 else volume
            if current_price > prev_close:
                bid_volumes = [int(avg_vol * 0.03 * (1.2 - i * 0.05)) for i in range(5)]
                ask_volumes = [int(avg_vol * 0.03 * (0.8 + i * 0.05)) for i in range(5)]
            else:
                bid_volumes = [int(avg_vol * 0.03 * (0.8 + i * 0.05)) for i in range(5)]
                ask_volumes = [int(avg_vol * 0.03 * (1.2 - i * 0.05)) for i in range(5)]

            # Build recent ticks from daily bars
            recent_ticks = []
            for i in range(-min(10, len(df)), 0):
                row = df.iloc[i]
                c = float(row["Close"])
                o = float(row["Open"])
                v = int(row["Volume"])
                side = "buy" if c >= o else "sell"
                recent_ticks.append({"price": round(c, 2), "volume": v, "side": side})

            # Previous day change for momentum
            prev_change = 0
            if len(closes) >= 3:
                prev_change = (closes[-2] - closes[-3]) / closes[-3] * 100

            # Fetch additional data in parallel (institutional, TAIEX, SOX)
            institutional_data, margin_data, taiex_data, sox_data = await self._fetch_extra_data(stock_id)

            market_data = MarketData(
                stock_id=stock_id,
                stock_name=self.get_stock_name(stock_id),
                current_price=current_price,
                prev_close=prev_close,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                volume=volume,
                outer_volume=outer_volume,
                inner_volume=inner_volume,
                bid_volumes=bid_volumes,
                ask_volumes=ask_volumes,
                recent_ticks=recent_ticks,
                minute_closes=closes,
                minute_highs=highs,
                minute_lows=lows,
                prev_minute_change_pct=prev_change,
                price_t_minus_2=closes[-3] if len(closes) >= 3 else None,
                price_t_minus_1=closes[-2] if len(closes) >= 2 else None,
                # New fields
                institutional_data=institutional_data,
                margin_data=margin_data,
                daily_volumes=volumes,
                taiex_current=taiex_data.get("current") if taiex_data else None,
                taiex_prev_close=taiex_data.get("prev_close") if taiex_data else None,
                sox_current=sox_data.get("current") if sox_data else None,
                sox_prev_close=sox_data.get("prev_close") if sox_data else None,
                market_timestamp=datetime.now(),
            )

            # During market hours: override current price/OHLCV with TWSE MIS real-time data
            if is_market_open():
                mkt = self.get_stock_market(stock_id)
                intraday = await self._twse_service.get_intraday_quote(stock_id, mkt)
                if intraday and intraday.get("current_price"):
                    market_data = dataclasses.replace(
                        market_data,
                        current_price=intraday["current_price"],
                        open_price=intraday.get("open") or market_data.open_price,
                        high_price=intraday.get("high") or market_data.high_price,
                        low_price=intraday.get("low") or market_data.low_price,
                        volume=intraday.get("volume") or market_data.volume,
                        market_timestamp=datetime.now(),
                    )

            # Cache only outside market hours; during market hours rely on raw_df_cache + intraday
            if not is_market_open():
                signal_cache[cache_key] = market_data
            return market_data

        except Exception as e:
            logger.error(f"Failed to get market data for {stock_id}: {e}")
            return self._empty_market_data(stock_id)

    async def _fetch_extra_data(self, stock_id: str) -> tuple:
        """Fetch institutional, margin, TAIEX and SOX data in parallel."""

        async def _get_institutional():
            try:
                return await self._twse_service.get_institutional_data(stock_id)
            except Exception as e:
                logger.debug(f"Institutional data unavailable: {e}")
                return None

        async def _get_margin():
            try:
                return await self._twse_service.get_margin_data(stock_id)
            except Exception as e:
                logger.debug(f"Margin data unavailable: {e}")
                return None

        async def _get_index(ticker: str):
            try:
                return self._fetch_index_data(ticker)
            except Exception as e:
                logger.debug(f"Index {ticker} data unavailable: {e}")
                return None

        results = await asyncio.gather(
            _get_institutional(),
            _get_margin(),
            _get_index("^TWII"),
            _get_index("^SOX"),
            return_exceptions=True,
        )

        # Replace exceptions with None
        return tuple(r if not isinstance(r, Exception) else None for r in results)

    def _fetch_index_data(self, ticker: str) -> Optional[dict]:
        """Fetch current and previous close for an index ticker."""
        cache_key = f"index:{ticker}"
        cached = signal_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            df = yf.download(ticker, period="5d", interval="1d", progress=False)
            df = _flatten_columns(df)
            if df.empty or len(df) < 2:
                return None
            result = {
                "current": round(float(df.iloc[-1]["Close"]), 2),
                "prev_close": round(float(df.iloc[-2]["Close"]), 2),
            }
            signal_cache[cache_key] = result
            return result
        except Exception as e:
            logger.debug(f"Failed to fetch index {ticker}: {e}")
            return None

    def _empty_market_data(self, stock_id: str) -> MarketData:
        """Return empty MarketData when data is unavailable."""
        return MarketData(
            stock_id=stock_id,
            stock_name=self.get_stock_name(stock_id),
            current_price=0,
            prev_close=0,
            open_price=0,
            high_price=0,
            low_price=0,
            volume=0,
        )

    async def get_fundamentals(self, stock_id: str) -> dict:
        """
        Get basic fundamentals via yfinance.Ticker.info.
        Cached in stock_info_cache for 24 hours.
        Rate-limit failures are cached for 5 minutes to avoid hammering Yahoo.
        """
        cache_key = f"fundamentals:{stock_id}"
        if cache_key in stock_info_cache:
            return stock_info_cache[cache_key]

        # Check negative cache (rate-limit cooldown, 5 min TTL)
        neg_key = f"fundamentals_fail:{stock_id}"
        if neg_key in rate_limit_cache:
            return {}

        try:
            ticker_sym = _get_ticker_symbol(stock_id)
            t = yf.Ticker(ticker_sym)
            raw = t.info or {}

            # Fallback to other market if primary returned nothing useful
            if not raw.get("trailingPE") and not raw.get("marketCap"):
                alt = f"{stock_id}.TWO" if ticker_sym.endswith(".TW") else f"{stock_id}.TW"
                try:
                    raw = yf.Ticker(alt).info or raw
                except Exception:
                    pass

            def _safe(key: str, default: float = 0.0) -> float:
                val = raw.get(key)
                if val is None:
                    return default
                try:
                    return round(float(val), 2)
                except (TypeError, ValueError):
                    return default

            # yfinance 1.2+ returns dividendYield as already-percentage (e.g. 1.23)
            # older versions returned fraction (0.0123). Detect by magnitude.
            raw_yield = raw.get("dividendYield") or 0
            if raw_yield and raw_yield < 1:
                div_yield = round(raw_yield * 100, 2)
            else:
                div_yield = round(raw_yield, 2)

            # --- Dividend history ---
            dividend_info = {
                "has_dividend": False,
                "last_dividend_amount": 0,
                "last_dividend_date": "",
                "dividend_frequency": 0,
                "dividend_months": [],
            }
            try:
                divs = t.dividends
                if divs is not None and len(divs) > 0:
                    dividend_info["has_dividend"] = True
                    # Last dividend
                    last_date = divs.index[-1]
                    dividend_info["last_dividend_amount"] = round(float(divs.iloc[-1]), 4)
                    dividend_info["last_dividend_date"] = last_date.strftime("%Y-%m-%d")
                    # Frequency & months from last 3 years
                    from datetime import datetime, timedelta
                    cutoff = datetime.now() - timedelta(days=365 * 3)
                    recent = divs[divs.index >= cutoff.strftime("%Y-%m-%d")]
                    if len(recent) > 0:
                        months = sorted(set(d.month for d in recent.index))
                        dividend_info["dividend_months"] = months
                        # Estimate annual frequency
                        years_span = max((recent.index[-1] - recent.index[0]).days / 365, 1)
                        dividend_info["dividend_frequency"] = round(len(recent) / years_span)
            except Exception:
                pass  # dividend data not available for some tickers

            fundamentals = {
                "pe": _safe("trailingPE"),
                "forward_pe": _safe("forwardPE"),
                "pb": _safe("priceToBook"),
                "eps": _safe("trailingEps"),
                "dividend_yield": div_yield,
                "market_cap": int(raw.get("marketCap") or 0),
                "week_52_high": _safe("fiftyTwoWeekHigh"),
                "week_52_low": _safe("fiftyTwoWeekLow"),
                "beta": _safe("beta"),
                "sector": raw.get("sector", "") or "",
                "industry": raw.get("industry", "") or "",
                **dividend_info,
            }
            stock_info_cache[cache_key] = fundamentals
            return fundamentals

        except Exception as e:
            err_msg = str(e)
            is_rate_limit = "rate" in err_msg.lower() or "too many" in err_msg.lower()
            if is_rate_limit:
                # Cache failure for 5 minutes to avoid hammering Yahoo
                rate_limit_cache[neg_key] = True
                logger.warning(f"Rate limited on fundamentals for {stock_id}, cooldown 5min")
            else:
                logger.warning(f"Failed to get fundamentals for {stock_id}: {e}")
            return {}

    async def get_history(self, stock_id: str, period: str = "3mo") -> list[dict]:
        """Fetch historical OHLCV data via yfinance (cached)."""
        cache_key = f"history:{stock_id}:{period}"
        if cache_key in history_cache:
            return history_cache[cache_key]

        try:
            df = _download_with_fallback(stock_id, period=period, interval="1d")
            if df.empty:
                return []
            records = []
            for idx, row in df.iterrows():
                records.append({
                    "date": idx.strftime("%Y-%m-%d"),
                    "open": round(float(row["Open"]), 2),
                    "high": round(float(row["High"]), 2),
                    "low": round(float(row["Low"]), 2),
                    "close": round(float(row["Close"]), 2),
                    "volume": int(row["Volume"]),
                })
            history_cache[cache_key] = records
            return records
        except Exception as e:
            logger.warning(f"yfinance fetch failed for {stock_id}: {e}")
            return []
