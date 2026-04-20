"""
/api/logs — 거래 로그 및 시스템 로그
"""
import os
from datetime import datetime, timedelta
from pathlib import Path
from fastapi import APIRouter, Query
from api.state import bot_state
from config import settings

router = APIRouter(prefix="/api/logs", tags=["logs"])

_LOG_DIR = settings.LOG_DIR


@router.get("/trades")
def get_trades(date: str = Query(None, description="YYYYMMDD, 기본값=오늘")):
    """당일 거래 기록 (메모리 기반)"""
    records = [t.__dict__ for t in bot_state.daily_trades]
    return {"trades": records, "count": len(records)}


@router.get("/system")
def get_system_logs(tail: int = Query(100, ge=1, le=500)):
    """최근 시스템 로그"""
    return {"logs": bot_state.get_logs(tail)}


@router.get("/daily-pnl")
def get_daily_pnl(days: int = Query(30, ge=1, le=90)):
    """날짜별 일일 손익 (trades_*.log 파일 파싱)"""
    result = []
    today = datetime.now()
    for i in range(days):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y%m%d")
        log_file = _LOG_DIR / f"trades_{date_str}.log"
        if log_file.exists():
            pnl = _parse_daily_pnl(log_file)
            result.append({"date": date.strftime("%m/%d"), "pnl": pnl})
        else:
            result.append({"date": date.strftime("%m/%d"), "pnl": 0})
    result.reverse()
    return {"daily_pnl": result}


def _parse_daily_pnl(log_file: Path) -> float:
    """trades 로그에서 실현 손익 합산"""
    total = 0.0
    try:
        content = log_file.read_text(encoding="utf-8")
        for line in content.splitlines():
            if "실현손익:" in line:
                # "실현손익: +12,345원" 형태에서 숫자 추출
                import re
                m = re.search(r"실현손익:\s*([+-]?[\d,]+)원", line)
                if m:
                    total += float(m.group(1).replace(",", ""))
    except Exception:
        pass
    return total
