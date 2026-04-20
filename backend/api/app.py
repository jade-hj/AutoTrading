"""
FastAPI 애플리케이션

실행: python server.py
     또는 uvicorn api.app:app --reload --port 8000
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from api.ws_manager import WebSocketManager
from api.state import bot_state
from api.routers import system, dashboard, positions, orders, scan, chart, logs
from utils.logger import setup_logger

setup_logger()
logger = logging.getLogger(__name__)


# ── 로그 핸들러 — logging → bot_state 버퍼 브리지 ─────────────

class _BotStateLogHandler(logging.Handler):
    """루트 로거의 출력을 bot_state.log_buffer 에도 복사한다."""
    def emit(self, record: logging.LogRecord):
        try:
            bot_state.push_log(
                level   = record.levelname,
                name    = record.name.split(".")[-1],
                message = self.format(record),
            )
        except Exception:
            pass

_state_handler = _BotStateLogHandler()
_state_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(_state_handler)


# ── Lifespan ────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    ws_manager = WebSocketManager()
    bot_state.ws_manager = ws_manager
    logger.info("FastAPI 서버 시작")
    yield
    # 종료 시 봇 정리
    if bot_state.is_running and bot_state.stop_event:
        bot_state.stop_event.set()
    logger.info("FastAPI 서버 종료")


# ── App ─────────────────────────────────────────────────────

app = FastAPI(
    title       = "AutoTrading API",
    description = "KRX 단타 자동매매 시스템 REST API",
    version     = "1.0.0",
    lifespan    = lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["http://localhost:5173", "http://localhost:3000"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

# ── 라우터 등록 ─────────────────────────────────────────────

app.include_router(system.router)
app.include_router(dashboard.router)
app.include_router(positions.router)
app.include_router(orders.router)
app.include_router(scan.router)
app.include_router(chart.router)
app.include_router(logs.router)


# ── WebSocket ───────────────────────────────────────────────

@app.websocket("/ws/updates")
async def ws_updates(websocket: WebSocket):
    """실시간 업데이트 스트림 (로그·거래·포지션)"""
    await bot_state.ws_manager.connect(websocket)
    try:
        while True:
            # 클라이언트 ping 처리 (연결 유지)
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        bot_state.ws_manager.disconnect(websocket)


# ── Health check ────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}
