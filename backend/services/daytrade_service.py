"""Day-trade candidate scanner: MA squeeze, institutional surge, price-volume divergence."""

import asyncio
from dataclasses import dataclass
from loguru import logger

from services.quote_service import QuoteService, KNOWN_STOCKS


@dataclass
class DayTradeSignal:
    name: str
    status: str  # "bullish" | "bearish" | "warning" | "neutral"
    value: float
    description: str


@dataclass
class DayTradeCandidate:
    stock_id: str
    stock_name: str
    current_price: float
    change_percent: float
    ma_squeeze: DayTradeSignal
    institutional: DayTradeSignal
    price_volume: DayTradeSignal
    score: float
    is_intraday: bool


class DayTradeService:
    def __init__(self, quote_service: QuoteService):
        self._qs = quote_service

    async def scan(self, stock_ids: list[str] | None = None) -> list[DayTradeCandidate]:
        """Scan stocks and return day-trade candidates sorted by signal strength."""
        if stock_ids is None:
            # Regular stocks only (4-digit codes), exclude ETFs
            stock_ids = [sid for sid in KNOWN_STOCKS if len(sid) == 4]

        tasks = [self._analyze_one(sid) for sid in stock_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        candidates = [r for r in results if isinstance(r, DayTradeCandidate)]
        candidates.sort(key=lambda c: abs(c.score), reverse=True)
        return candidates

    async def _analyze_one(self, stock_id: str) -> DayTradeCandidate | None:
        try:
            market_data = await self._qs.get_market_data(stock_id)
            quote = await self._qs.get_quote(stock_id)

            closes = market_data.minute_closes
            volumes = market_data.daily_volumes or []

            if not closes or len(closes) < 15:
                return None

            ma_sig = self._calc_ma_squeeze(closes, volumes)
            inst_sig = self._calc_institutional(market_data.institutional_data)
            pv_sig = self._calc_price_volume(closes, volumes)

            score_map = {"bullish": 1.0, "neutral": 0.0, "warning": -0.5, "bearish": -1.0}
            score = (
                score_map.get(ma_sig.status, 0) * 40 +
                score_map.get(inst_sig.status, 0) * 35 +
                score_map.get(pv_sig.status, 0) * 25
            )

            return DayTradeCandidate(
                stock_id=stock_id,
                stock_name=self._qs.get_stock_name(stock_id),
                current_price=market_data.current_price,
                change_percent=quote.get("change_percent", 0),
                ma_squeeze=ma_sig,
                institutional=inst_sig,
                price_volume=pv_sig,
                score=round(score, 1),
                is_intraday=quote.get("is_intraday", False),
            )
        except Exception as e:
            logger.debug(f"DayTrade scan skipped {stock_id}: {e}")
            return None

    def _calc_ma_squeeze(self, closes: list[float], volumes: list[int]) -> DayTradeSignal:
        """MA5/MA10 squeeze (gap < 0.8% for 2+ days) followed by volume breakout."""
        if len(closes) < 15:
            return DayTradeSignal("均線糾結突破", "neutral", 0.0, "資料不足")

        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10
        current = closes[-1]

        # Count squeeze days (last 3 days before today)
        squeeze_days = 0
        for offset in range(1, 4):
            idx = -offset - 1
            if len(closes) < abs(idx) + 10:
                continue
            m5 = sum(closes[idx - 4:idx + 1]) / 5
            m10 = sum(closes[idx - 9:idx + 1]) / 10
            if m10 > 0 and abs(m5 - m10) / m10 < 0.008:
                squeeze_days += 1

        avg_vol = sum(volumes[-6:-1]) / 5 if len(volumes) >= 6 else 0
        today_vol = volumes[-1] if volumes else 0
        vol_ratio = today_vol / avg_vol if avg_vol > 0 else 1.0
        gap_pct = (ma5 - ma10) / ma10 * 100 if ma10 > 0 else 0.0

        if squeeze_days >= 2:
            if current > ma5 and current > ma10 and vol_ratio >= 1.4:
                return DayTradeSignal("均線糾結突破", "bullish", round(vol_ratio, 2),
                    f"糾結 {squeeze_days} 天後向上突破，量比 {vol_ratio:.1f}x")
            elif current < ma5 and current < ma10 and vol_ratio >= 1.4:
                return DayTradeSignal("均線糾結突破", "bearish", round(vol_ratio, 2),
                    f"糾結 {squeeze_days} 天後向下跌破，量比 {vol_ratio:.1f}x")
            else:
                return DayTradeSignal("均線糾結突破", "neutral", round(vol_ratio, 2),
                    f"均線糾結中（差 {gap_pct:.2f}%），待突破")
        else:
            return DayTradeSignal("均線糾結突破", "neutral", round(abs(gap_pct), 2),
                f"MA5-MA10 差 {gap_pct:.2f}%，未糾結")

    def _calc_institutional(self, inst: dict | None) -> DayTradeSignal:
        """Detect unusual institutional net buying/selling."""
        if not inst:
            return DayTradeSignal("籌碼異動", "neutral", 0.0, "無法人資料")

        foreign_net = inst.get("foreign_net", 0)
        trust_net = inst.get("trust_net", 0)
        total_net = inst.get("total_net", 0)

        if total_net > 10000:
            return DayTradeSignal("籌碼異動", "bullish", float(total_net),
                f"法人大買超 {total_net:,} 張（外資 {foreign_net:+,}，投信 {trust_net:+,}）")
        elif total_net > 3000:
            return DayTradeSignal("籌碼異動", "bullish", float(total_net),
                f"法人買超 {total_net:,} 張")
        elif total_net < -10000:
            return DayTradeSignal("籌碼異動", "bearish", float(total_net),
                f"法人大賣超 {total_net:,} 張")
        elif total_net < -3000:
            return DayTradeSignal("籌碼異動", "bearish", float(total_net),
                f"法人賣超 {total_net:,} 張")
        else:
            return DayTradeSignal("籌碼異動", "neutral", float(total_net),
                f"法人小幅異動 {total_net:+,} 張")

    def _calc_price_volume(self, closes: list[float], volumes: list[int]) -> DayTradeSignal:
        """Detect price-volume divergence."""
        if len(closes) < 6 or len(volumes) < 6:
            return DayTradeSignal("價量關係", "neutral", 0.0, "資料不足")

        current = closes[-1]
        prev = closes[-2]
        today_vol = volumes[-1]
        avg_vol = sum(volumes[-6:-1]) / 5

        if avg_vol == 0:
            return DayTradeSignal("價量關係", "neutral", 0.0, "無成交量")

        vol_ratio = today_vol / avg_vol
        price_chg = (current - prev) / prev * 100 if prev > 0 else 0.0

        if price_chg > 0.5 and vol_ratio >= 1.3:
            return DayTradeSignal("價量關係", "bullish", round(vol_ratio, 2),
                f"價漲量增，量比 {vol_ratio:.1f}x，健康上漲")
        elif price_chg > 0.5 and vol_ratio < 0.7:
            return DayTradeSignal("價量關係", "warning", round(vol_ratio, 2),
                f"價漲量縮，量比 {vol_ratio:.1f}x，漲勢不穩")
        elif price_chg < -0.5 and vol_ratio >= 1.5:
            return DayTradeSignal("價量關係", "bearish", round(vol_ratio, 2),
                f"價跌量增，量比 {vol_ratio:.1f}x，賣壓沉重")
        elif price_chg < -0.5 and vol_ratio < 0.6:
            return DayTradeSignal("價量關係", "neutral", round(vol_ratio, 2),
                f"價跌量縮，量比 {vol_ratio:.1f}x，縮量整理")
        else:
            return DayTradeSignal("價量關係", "neutral", round(vol_ratio, 2),
                f"量比 {vol_ratio:.1f}x，無明顯背離")
