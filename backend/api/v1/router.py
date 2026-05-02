"""Combine all v1 API routers."""

from fastapi import APIRouter

from api.v1.stocks import router as stocks_router
from api.v1.analysis import router as analysis_router
from api.v1.portfolio import router as portfolio_router
from api.v1.predictions import router as predictions_router
from api.v1.stats import router as stats_router
from api.v1.daytrade import router as daytrade_router

api_v1_router = APIRouter(prefix="/api/v1")

api_v1_router.include_router(stocks_router)
api_v1_router.include_router(analysis_router)
api_v1_router.include_router(portfolio_router)
api_v1_router.include_router(predictions_router)
api_v1_router.include_router(stats_router)
api_v1_router.include_router(daytrade_router)
