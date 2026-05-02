"""Day-trade scanning API endpoint."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

from services.daytrade_service import DayTradeService
from services.quote_service import QuoteService

router = APIRouter(prefix="/daytrade", tags=["daytrade"])

_quote_service = QuoteService()
_daytrade_service = DayTradeService(_quote_service)


@router.get("/scan")
async def scan_daytrade(
    stocks: Optional[str] = Query(None, description="逗號分隔股票代號，預設掃描所有主要股票"),
):
    """Scan stocks for day-trade signals: MA squeeze, institutional surge, price-volume divergence."""
    stock_ids = [s.strip() for s in stocks.split(",")] if stocks else None
    candidates = await _daytrade_service.scan(stock_ids)

    return {
        "success": True,
        "data": [
            {
                "stock_id": c.stock_id,
                "stock_name": c.stock_name,
                "current_price": c.current_price,
                "change_percent": c.change_percent,
                "score": c.score,
                "is_intraday": c.is_intraday,
                "signals": {
                    "ma_squeeze": {
                        "status": c.ma_squeeze.status,
                        "value": c.ma_squeeze.value,
                        "description": c.ma_squeeze.description,
                    },
                    "institutional": {
                        "status": c.institutional.status,
                        "value": c.institutional.value,
                        "description": c.institutional.description,
                    },
                    "price_volume": {
                        "status": c.price_volume.status,
                        "value": c.price_volume.value,
                        "description": c.price_volume.description,
                    },
                },
            }
            for c in candidates
        ],
        "count": len(candidates),
        "timestamp": datetime.now().isoformat(),
    }
