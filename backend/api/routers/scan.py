"""
/api/scan — 종목 스캔 및 Agent 분석
"""
import asyncio
from fastapi import APIRouter, HTTPException
from api.state import bot_state

router = APIRouter(prefix="/api/scan", tags=["scan"])


@router.get("/candidates")
def get_candidates():
    """마지막 스캔 결과 반환"""
    return {
        "candidates":  bot_state.last_scan_candidates,
        "scanned_at":  (
            bot_state.last_scan_time.strftime("%H:%M:%S")
            if bot_state.last_scan_time else None
        ),
        "count": len(bot_state.last_scan_candidates),
    }


@router.post("/run")
async def run_scan():
    """즉시 스캔 실행 (5분 주기 외 수동 트리거)"""
    from data.market_scanner import scan_candidates
    from datetime import datetime
    try:
        loop = asyncio.get_event_loop()
        candidates = await loop.run_in_executor(None, scan_candidates)
        bot_state.last_scan_candidates = candidates
        bot_state.last_scan_time = datetime.now()
        return {
            "ok": True,
            "count": len(candidates),
            "candidates": candidates,
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@router.get("/analyze/{stock_code}")
async def analyze_stock(stock_code: str):
    """특정 종목 3-Agent 분석 실행"""
    if bot_state.coordinator is None:
        raise HTTPException(400, "봇이 실행 중이 아닙니다. 먼저 시작해주세요.")

    # 후보 목록에서 해당 종목 찾기
    candidate = next(
        (c for c in bot_state.last_scan_candidates
         if c["stock_code"] == stock_code), None
    )
    if candidate is None:
        raise HTTPException(404, f"스캔 결과에 없는 종목: {stock_code}. 먼저 스캔을 실행하세요.")

    from kis import rest_client as kis
    from data.indicators import get_all_indicators
    from agents.base_agent import ScalpingContext
    from config import settings

    try:
        candles = kis.get_minute_ohlcv(stock_code, count=settings.SCALPING_CANDLE_COUNT)
        balance = kis.get_balance()
        kospi_rate = kis.get_kospi_change_rate()
        indicators = get_all_indicators(candles) if candles else {}

        volumes = [c["volume"] for c in candles if c["volume"] > 0]
        if len(volumes) >= 10:
            recent = volumes[-5:]
            prior  = volumes[-25:-5] or volumes[:-5]
            volume_ratio = (sum(recent)/len(recent)) / (sum(prior)/len(prior)) if prior else 1.0
        else:
            avg = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else 1
            volume_ratio = volumes[-1] / avg if avg else 1.0

        ctx = ScalpingContext(
            stock_code        = stock_code,
            stock_name        = candidate["stock_name"],
            current_price     = candidate["current_price"],
            change_rate       = candidate["change_rate"],
            open_price        = candles[0]["open"] if candles else candidate["current_price"],
            minute_candles    = candles,
            indicators        = indicators,
            volume_ratio      = volume_ratio,
            available_cash    = balance["available_cash"],
            holdings          = balance["holdings"],
            holding_count     = len(balance["holdings"]),
            kospi_change_rate = kospi_rate,
        )

        result = await bot_state.coordinator.run(ctx)
        return {
            "stock_code":   stock_code,
            "stock_name":   candidate["stock_name"],
            "action":       result.action,
            "executed":     result.executed,
            "reason":       result.reason,
            "signal": {
                "action":     str(result.signal.action) if result.signal else None,
                "confidence": result.signal.confidence if result.signal else None,
                "reasoning":  result.signal.reasoning if result.signal else None,
            } if result.signal else None,
            "risk": {
                "approved":   result.risk.approved if result.risk else None,
                "quantity":   result.risk.quantity if result.risk else None,
                "stop_loss":  result.risk.stop_loss_price if result.risk else None,
                "tp1":        result.risk.take_profit_1_price if result.risk else None,
                "tp2":        result.risk.take_profit_2_price if result.risk else None,
                "reasoning":  result.risk.reasoning if result.risk else None,
            } if result.risk else None,
            "market": {
                "go":         result.market.go if result.market else None,
                "confidence": result.market.confidence if result.market else None,
                "reasoning":  result.market.reasoning if result.market else None,
            } if result.market else None,
        }
    except Exception as e:
        raise HTTPException(500, str(e))
