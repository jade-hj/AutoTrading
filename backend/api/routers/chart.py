"""
/api/chart — 차트 데이터 및 기술적 지표
"""
from fastapi import APIRouter, Query
from kis import rest_client as kis
from data.indicators import get_all_indicators

router = APIRouter(prefix="/api/chart", tags=["chart"])


@router.get("/{stock_code}/candles")
def get_minute_candles(stock_code: str, count: int = Query(40, ge=5, le=200)):
    """분봉 OHLCV"""
    candles = kis.get_minute_ohlcv(stock_code, count=count)
    return {"stock_code": stock_code, "candles": candles, "count": len(candles)}


@router.get("/{stock_code}/daily")
def get_daily_candles(
    stock_code: str,
    count: int   = Query(60, ge=5, le=200),
    period: str  = Query("D", regex="^[DWM]$"),
):
    """일/주/월봉 OHLCV"""
    candles = kis.get_ohlcv(stock_code, period=period, count=count)
    return {"stock_code": stock_code, "candles": candles, "count": len(candles)}


@router.get("/{stock_code}/indicators")
def get_indicators(stock_code: str, count: int = Query(40, ge=20, le=200)):
    """RSI, MACD, 이동평균, 볼린저밴드"""
    candles = kis.get_minute_ohlcv(stock_code, count=count)
    indicators = get_all_indicators(candles) if candles else {}
    return {"stock_code": stock_code, "indicators": indicators}


@router.get("/{stock_code}/price")
def get_current_price(stock_code: str):
    """현재가 조회"""
    return kis.get_current_price(stock_code)
