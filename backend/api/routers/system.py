"""
/api/system — 봇 제어 및 설정
"""
import asyncio
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.state import bot_state
from config import settings

router = APIRouter(prefix="/api/system", tags=["system"])
logger = logging.getLogger(__name__)


# ── GET /api/system/status ───────────────────────────────────

@router.get("/status")
def get_status():
    return bot_state.status_dict()


# ── POST /api/system/start ───────────────────────────────────

@router.post("/start")
async def start_bot():
    if bot_state.is_running:
        raise HTTPException(400, "이미 실행 중입니다")

    from agents.scalping_coordinator import ScalpingCoordinator
    from trading.position_tracker import ScalpingPositionTracker
    from api.bot_runner import run_scanning_loop, run_monitor_loop

    bot_state.stop_event  = asyncio.Event()
    bot_state.coordinator = ScalpingCoordinator()
    bot_state.tracker     = ScalpingPositionTracker()
    bot_state.is_running  = True

    from datetime import datetime
    bot_state.start_time = datetime.now()

    loop = asyncio.get_event_loop()
    bot_state.scan_task    = loop.create_task(
        run_scanning_loop(bot_state.coordinator, bot_state.tracker, bot_state.stop_event)
    )
    bot_state.monitor_task = loop.create_task(
        run_monitor_loop(bot_state.tracker, bot_state.stop_event)
    )
    logger.info("[System] 봇 시작")
    return {"ok": True, "message": "봇이 시작되었습니다"}


# ── POST /api/system/stop ────────────────────────────────────

@router.post("/stop")
async def stop_bot():
    if not bot_state.is_running:
        raise HTTPException(400, "실행 중이 아닙니다")

    bot_state.stop_event.set()
    for task in (bot_state.scan_task, bot_state.monitor_task):
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    bot_state.is_running   = False
    bot_state.scan_task    = None
    bot_state.monitor_task = None
    bot_state.stop_event   = None
    logger.info("[System] 봇 중지")
    return {"ok": True, "message": "봇이 중지되었습니다"}


# ── GET /api/system/settings ─────────────────────────────────

@router.get("/settings")
def get_settings():
    return {
        "scan": {
            "scan_top_n":        settings.SCAN_TOP_N,
            "scan_min_price":    settings.SCAN_MIN_PRICE,
            "scan_min_volume":   settings.SCAN_MIN_VOLUME,
            "scan_markets":      settings.SCAN_MARKETS,
        },
        "common": {
            "interval_sec":       settings.SCALPING_INTERVAL_SEC,
            "monitor_sec":        settings.SCALPING_MONITOR_SEC,
            "max_positions":      settings.SCALPING_MAX_POSITIONS,
            "position_ratio":     settings.SCALPING_POSITION_RATIO,
            "stop_loss":          settings.SCALPING_STOP_LOSS,
            "take_profit_1":      settings.SCALPING_TAKE_PROFIT_1,
            "take_profit_2":      settings.SCALPING_TAKE_PROFIT_2,
            "daily_loss_limit":   settings.SCALPING_DAILY_LOSS_LIMIT,
            "kospi_range":        settings.SCALPING_KOSPI_RANGE,
            "exec_start":         settings.SCALPING_EXEC_START,
            "exec_end":           settings.SCALPING_EXEC_END,
        },
        "am": {
            "end":              settings.SCALPING_AM_END,
            "volume_surge":     settings.SCALPING_AM_VOLUME_SURGE,
            "rsi_min":          settings.SCALPING_AM_RSI_MIN,
            "rsi_max":          settings.SCALPING_AM_RSI_MAX,
            "change_rate_max":  settings.SCALPING_AM_CHANGE_RATE_MAX,
            "gap_limit":        settings.SCALPING_AM_GAP_LIMIT,
        },
        "pm": {
            "start":            settings.SCALPING_PM_START,
            "volume_surge":     settings.SCALPING_PM_VOLUME_SURGE,
            "rsi_min":          settings.SCALPING_PM_RSI_MIN,
            "rsi_max":          settings.SCALPING_PM_RSI_MAX,
            "change_rate_min":  settings.SCALPING_PM_CHANGE_RATE_MIN,
            "change_rate_max":  settings.SCALPING_PM_CHANGE_RATE_MAX,
            "gap_limit":        settings.SCALPING_PM_GAP_LIMIT,
        },
    }


# ── PATCH /api/system/settings ───────────────────────────────

class SettingsPatch(BaseModel):
    key:   str
    value: float | int | str

_PATCHABLE = {
    "SCALPING_AM_VOLUME_SURGE", "SCALPING_PM_VOLUME_SURGE",
    "SCALPING_AM_RSI_MIN", "SCALPING_AM_RSI_MAX",
    "SCALPING_PM_RSI_MIN", "SCALPING_PM_RSI_MAX",
    "SCALPING_AM_CHANGE_RATE_MAX",
    "SCALPING_PM_CHANGE_RATE_MIN", "SCALPING_PM_CHANGE_RATE_MAX",
    "SCALPING_AM_GAP_LIMIT", "SCALPING_PM_GAP_LIMIT",
    "SCALPING_STOP_LOSS", "SCALPING_TAKE_PROFIT_1", "SCALPING_TAKE_PROFIT_2",
    "SCALPING_MAX_POSITIONS", "SCAN_TOP_N",
}

@router.patch("/settings")
def patch_settings(body: SettingsPatch):
    key = body.key.upper()
    if key not in _PATCHABLE:
        raise HTTPException(400, f"변경 불가 항목: {key}")
    if not hasattr(settings, key):
        raise HTTPException(404, f"설정 항목 없음: {key}")
    setattr(settings, key, body.value)
    return {"ok": True, "key": key, "value": body.value}
