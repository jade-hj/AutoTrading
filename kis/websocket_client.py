"""
KIS Open API - WebSocket 실시간 시세 클라이언트

구독한 종목의 체결가를 비동기로 수신해 콜백에 전달한다.

참고:
  - 실전: ws://ops.koreainvestment.com:21000
  - 모의: ws://ops.koreainvestment.com:31000
  - TR_ID H0STCNT0: 주식 체결 (실시간)
"""

import asyncio
import json
import logging
from typing import Awaitable, Callable

import websockets

from config import settings
from kis.auth import get_auth

logger = logging.getLogger(__name__)

TR_PRICE = "H0STCNT0"   # 주식 체결


class KISWebSocket:
    """KIS 실시간 시세 WebSocket 클라이언트."""

    def __init__(self):
        self._running = False
        self._price_cache: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # 공개 인터페이스
    # ------------------------------------------------------------------

    async def connect(
        self,
        stock_codes: list[str],
        on_price: Callable[[dict], Awaitable[None]],
    ) -> None:
        """WebSocket에 연결하고 종목을 구독한다.

        Args:
            stock_codes: 구독할 종목 코드 목록
            on_price:    체결가 수신 시 호출되는 비동기 콜백
                         콜백 인자: {stock_code, current_price, change_rate,
                                    volume, trade_time}
        """
        approval_key = get_auth().get_ws_approval_key()
        self._running = True

        async for ws in websockets.connect(
            settings.KIS_WS_URL,
            ping_interval=30,
            ping_timeout=10,
        ):
            try:
                logger.info("KIS WebSocket 연결: %s", settings.KIS_WS_URL)
                for code in stock_codes:
                    await self._subscribe(ws, approval_key, code)

                async for raw in ws:
                    if not self._running:
                        return
                    await self._handle(raw, on_price)

            except websockets.ConnectionClosed:
                if not self._running:
                    return
                logger.warning("WebSocket 연결 끊김, 재연결 시도...")
                await asyncio.sleep(3)

    def get_latest(self, stock_code: str) -> dict | None:
        """마지막으로 수신된 체결가 데이터를 반환한다."""
        return self._price_cache.get(stock_code)

    def stop(self) -> None:
        """수신 루프를 종료한다."""
        self._running = False

    # ------------------------------------------------------------------
    # 내부 처리
    # ------------------------------------------------------------------

    async def _subscribe(self, ws, approval_key: str, stock_code: str) -> None:
        msg = {
            "header": {
                "approval_key": approval_key,
                "custtype":     "P",
                "tr_type":      "1",
                "content-type": "utf-8",
            },
            "body": {
                "input": {
                    "tr_id":  TR_PRICE,
                    "tr_key": stock_code,
                },
            },
        }
        await ws.send(json.dumps(msg))
        logger.debug("구독 등록: %s", stock_code)

    async def _handle(
        self,
        raw: str,
        on_price: Callable[[dict], Awaitable[None]],
    ) -> None:
        # JSON 형식 = 시스템 메시지 (PINGPONG 등)
        if raw.startswith("{"):
            msg = json.loads(raw)
            tr_id = msg.get("header", {}).get("tr_id", "")
            if tr_id == "PINGPONG":
                await self._ws_ref.send(raw)
            return

        # 데이터 형식: `0|{TR_ID}|{count}|{fields^separated}`
        parts = raw.split("|")
        if len(parts) < 4:
            return

        tr_id   = parts[1]
        payload = parts[3]

        if tr_id == TR_PRICE:
            data = self._parse_price(payload)
            if data:
                self._price_cache[data["stock_code"]] = data
                await on_price(data)

    @staticmethod
    def _parse_price(payload: str) -> dict | None:
        """
        H0STCNT0 체결 데이터 파싱.

        주요 필드 인덱스 (^구분):
          0: 종목코드, 1: 체결시간, 2: 현재가, 5: 전일대비율, 13: 누적거래량
        """
        fields = payload.split("^")
        if len(fields) < 14:
            return None
        try:
            return {
                "stock_code":    fields[0],
                "trade_time":    fields[1],
                "current_price": int(fields[2]),
                "change_rate":   float(fields[5]),
                "volume":        int(fields[13]),
            }
        except (ValueError, IndexError):
            return None
