"""
봇 전역 상태 싱글턴

FastAPI 서버와 트레이딩 봇이 공유하는 상태 객체.
API 엔드포인트에서 bot_state 를 import 해서 읽고 쓴다.
"""
import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)

LOG_BUFFER_SIZE = 500   # 메모리에 보관할 최근 로그 줄 수


@dataclass
class TradeRecord:
    """당일 매매 기록 1건"""
    timestamp:   str
    action:      str          # BUY | SELL
    stock_code:  str
    stock_name:  str
    price:       int
    quantity:    int
    pnl:         float = 0.0  # 매도 시 실현 손익 (원)
    pnl_rate:    float = 0.0  # 매도 시 실현 손익률 (%)
    order_no:    str  = ""
    reason:      str  = ""


class BotState:
    """트레이딩 봇 런타임 상태"""

    def __init__(self):
        self.is_running: bool = False
        self.start_time: Optional[datetime] = None

        # asyncio 태스크 핸들
        self.stop_event: Optional[asyncio.Event]  = None
        self.scan_task:  Optional[asyncio.Task]   = None
        self.monitor_task: Optional[asyncio.Task] = None

        # 컴포넌트 참조 (start 시 주입)
        self.coordinator = None   # ScalpingCoordinator
        self.tracker     = None   # ScalpingPositionTracker

        # 스캔 캐시
        self.last_scan_candidates: list[dict] = []
        self.last_scan_time: Optional[datetime] = None

        # 당일 거래 기록
        self.daily_trades: list[TradeRecord] = []
        self.daily_realized_pnl: float = 0.0   # 당일 실현 손익 합계 (원)

        # 당일 손절 종목 재매수 금지 목록
        self.daily_blocked_codes: set[str] = set()

        # 로그 버퍼 (최근 N줄)
        self._log_buffer: deque[dict] = deque(maxlen=LOG_BUFFER_SIZE)

        # WebSocket 연결 관리자 (app.py 에서 주입)
        self.ws_manager = None

    # ── 로그 버퍼 ──────────────────────────────────────────────

    def push_log(self, level: str, name: str, message: str) -> None:
        entry = {
            "ts":      datetime.now().strftime("%H:%M:%S"),
            "level":   level,
            "name":    name,
            "message": message,
        }
        self._log_buffer.append(entry)
        if self.ws_manager:
            asyncio.create_task(self.ws_manager.broadcast({"type": "log", "data": entry}))

    def get_logs(self, tail: int = 100) -> list[dict]:
        buf = list(self._log_buffer)
        return buf[-tail:]

    # ── 거래 기록 ──────────────────────────────────────────────

    def record_buy(self, **kwargs) -> None:
        rec = TradeRecord(
            timestamp  = datetime.now().strftime("%H:%M:%S"),
            action     = "BUY",
            **kwargs,
        )
        self.daily_trades.append(rec)
        if self.ws_manager:
            asyncio.create_task(self.ws_manager.broadcast({
                "type": "trade",
                "data": rec.__dict__,
            }))

    def record_sell(self, **kwargs) -> None:
        rec = TradeRecord(
            timestamp = datetime.now().strftime("%H:%M:%S"),
            action    = "SELL",
            **kwargs,
        )
        self.daily_trades.append(rec)
        self.daily_realized_pnl += rec.pnl
        if self.ws_manager:
            asyncio.create_task(self.ws_manager.broadcast({
                "type": "trade",
                "data": rec.__dict__,
            }))

    # ── 포지션 현황 ────────────────────────────────────────────

    def get_positions(self) -> list[dict]:
        """ScalpingPositionTracker._positions 를 직렬화해 반환"""
        if self.tracker is None:
            return []
        result = []
        for code, pos in self.tracker._positions.items():
            result.append({
                "stock_code":   code,
                "stock_name":   pos.get("stock_name", ""),
                "quantity":     pos.get("quantity", 0),
                "entry_price":  pos.get("entry_price", 0),
                "stop_loss":    pos.get("stop_loss", 0),
                "tp1":          pos.get("tp1", 0),
                "tp2":          pos.get("tp2", 0),
                "tp1_hit":      pos.get("tp1_hit", False),
            })
        return result

    # ── 상태 요약 ──────────────────────────────────────────────

    def status_dict(self) -> dict:
        from agents.filter_agent import _get_session
        uptime = None
        if self.start_time:
            delta = datetime.now() - self.start_time
            uptime = int(delta.total_seconds())

        return {
            "is_running":  self.is_running,
            "mode":        "모의투자" if settings.KIS_IS_VIRTUAL else "실전투자",
            "session":     _get_session() if self.is_running else "-",
            "uptime_sec":  uptime,
            "start_time":  self.start_time.strftime("%H:%M:%S") if self.start_time else None,
            "position_count": len(self.get_positions()),
            "daily_pnl":   self.daily_realized_pnl,
            "last_scan_time": (
                self.last_scan_time.strftime("%H:%M:%S")
                if self.last_scan_time else None
            ),
        }


# 모듈 레벨 싱글턴
bot_state = BotState()
