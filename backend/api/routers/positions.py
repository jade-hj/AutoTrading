"""
/api/positions — 보유 포지션 조회 및 수동 청산
"""
from fastapi import APIRouter, HTTPException
from kis import rest_client as kis
from api.state import bot_state

router = APIRouter(prefix="/api/positions", tags=["positions"])


@router.get("")
def get_positions():
    """현재 추적 중인 포지션 목록 + 현재가 조회"""
    positions = bot_state.get_positions()
    enriched = []
    for pos in positions:
        try:
            price_data = kis.get_current_price(pos["stock_code"])
            current = price_data["current_price"]
        except Exception:
            current = pos["entry_price"]

        entry = pos["entry_price"]
        pnl_rate = (current - entry) / entry * 100 if entry else 0
        enriched.append({
            **pos,
            "current_price": current,
            "pnl_rate":      round(pnl_rate, 2),
            "pnl":           (current - entry) * pos["quantity"],
        })
    return enriched


@router.get("/{stock_code}")
def get_position(stock_code: str):
    positions = bot_state.get_positions()
    pos = next((p for p in positions if p["stock_code"] == stock_code), None)
    if pos is None:
        raise HTTPException(404, f"포지션 없음: {stock_code}")
    try:
        price_data = kis.get_current_price(stock_code)
        current = price_data["current_price"]
    except Exception:
        current = pos["entry_price"]
    entry = pos["entry_price"]
    return {
        **pos,
        "current_price": current,
        "pnl_rate":      round((current - entry) / entry * 100, 2) if entry else 0,
        "pnl":           (current - entry) * pos["quantity"],
    }


@router.delete("/{stock_code}")
def close_position(stock_code: str):
    """수동 즉시 청산 (시장가 매도)"""
    positions = bot_state.get_positions()
    pos = next((p for p in positions if p["stock_code"] == stock_code), None)
    if pos is None:
        raise HTTPException(404, f"포지션 없음: {stock_code}")
    try:
        order = kis.place_order(stock_code, "SELL", pos["quantity"], price=0)
        if bot_state.tracker:
            bot_state.tracker.unregister(stock_code)
        return {"ok": True, "order_no": order["order_no"]}
    except Exception as e:
        raise HTTPException(500, str(e))
