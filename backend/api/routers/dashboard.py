"""
/api/dashboard — 대시보드 요약 데이터
"""
from fastapi import APIRouter
from kis import rest_client as kis

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary")
def get_summary():
    """예수금, 총평가, 당일 손익, 보유 종목 수"""
    from api.state import bot_state
    balance = kis.get_balance()
    return {
        "available_cash":  balance["available_cash"],
        "total_eval":      balance["total_eval"],
        "holdings_count":  len(balance["holdings"]),
        "daily_pnl":       bot_state.daily_realized_pnl,
        "daily_loss_limit_reached": (
            bot_state.tracker.is_daily_loss_limit_reached()
            if bot_state.tracker else False
        ),
    }


@router.get("/kospi")
def get_kospi():
    """코스피 지수 현황"""
    return kis.get_kospi_index()
