"""
WebSocket 연결 관리자

연결된 모든 클라이언트에게 메시지를 브로드캐스트한다.
"""
import json
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info("[WS] 연결 (%d 총)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws) if hasattr(self._connections, 'discard') \
            else self._connections.remove(ws) if ws in self._connections else None
        logger.info("[WS] 해제 (%d 총)", len(self._connections))

    async def broadcast(self, data: dict) -> None:
        if not self._connections:
            return
        msg = json.dumps(data, ensure_ascii=False)
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self._connections:
                self._connections.remove(ws)
