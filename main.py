"""
주식 자동 매매 시스템 — 진입점

실행 흐름:
1. 장 운영 시간 확인 (09:00 ~ 15:30)
2. KIS WebSocket으로 실시간 시세 수신 시작
3. ORDER_INTERVAL_SEC 마다:
   a. 종목 스캔
   b. 포지션 조회
   c. AI Agent 토론 → 합의
   d. 주문 실행
"""
import asyncio
import signal
from datetime import datetime, time as dtime
import logging
from config import settings
from data.market_scanner import scan_candidates, format_candidates_for_agent
from agents.base_agent import MarketContext
from agents.claude_agent import ClaudeAgent
from agents.gpt_agent import GPTAgent
from agents.gemini_agent import GeminiAgent
from agents.moderator import Moderator
from agents.consensus import decide
from trading.position_tracker import PositionTracker
from trading.order_manager import OrderManager
from kis.websocket_client import KISWebSocket

logger      = logging.getLogger(__name__)
trade_log   = logging.getLogger("trade")

# ── 장 운영 시간 ──────────────────────────────────────────────
MARKET_OPEN  = dtime(9, 0)
MARKET_CLOSE = dtime(15, 30)


def is_market_open() -> bool:
    now = datetime.now().time()
    return MARKET_OPEN <= now <= MARKET_CLOSE


# ── 메인 루프 ─────────────────────────────────────────────────

async def trading_loop(
    moderator: Moderator,
    tracker: PositionTracker,
    ws_client: KISWebSocket,
    stop_event: asyncio.Event,
) -> None:
    """ORDER_INTERVAL_SEC 마다 합의체를 실행해 주문을 처리한다."""
    logger.info("자동 매매 루프 시작")

    while not stop_event.is_set():
        try:
            if not is_market_open():
                logger.info("장 외 시간 — 대기 중")
                await asyncio.sleep(60)
                continue

            # ── 종목 스캔 ────────────────────────────────────
            logger.info("종목 스캔 시작")
            candidates = scan_candidates()
            if not candidates:
                logger.warning("후보 종목 없음 — 다음 주기 대기")
                await asyncio.sleep(settings.ORDER_INTERVAL_SEC)
                continue

            # 실시간 WebSocket 가격으로 현재가 업데이트
            for c in candidates:
                latest = ws_client.get_latest_price(c["stock_code"])
                if latest:
                    c["current_price"] = latest["current_price"]
                    c["volume"]        = latest["volume"]

            candidates_text = format_candidates_for_agent(candidates)

            # ── 포지션 조회 ──────────────────────────────────
            portfolio = tracker.refresh()

            context = MarketContext(
                candidates       = candidates,
                candidates_text  = candidates_text,
                current_holdings = portfolio.holdings,
                available_cash   = portfolio.available_cash,
                total_portfolio  = portfolio.total_value,
            )

            # ── AI 토론 & 합의 ───────────────────────────────
            debate_result = await moderator.run_debate(context)
            consensus     = decide(debate_result.final_votes)

            # ── 주문 실행 ────────────────────────────────────
            order_mgr = OrderManager(portfolio)
            executed  = order_mgr.execute(consensus)

            # 거래 로그
            trade_log.info(
                f"합의: {consensus.action} {consensus.stock_code} "
                f"({consensus.vote_count}/{consensus.total_agents}표) | "
                f"실행 주문: {len(executed)}건"
            )
            for order in executed:
                trade_log.info(f"  주문: {order}")

        except Exception as e:
            logger.error(f"매매 루프 오류: {e}", exc_info=True)

        await asyncio.sleep(settings.ORDER_INTERVAL_SEC)


async def main() -> None:
    logger.info("=" * 60)
    logger.info("주식 자동 매매 시스템 시작")
    logger.info(f"모드: {'모의투자' if settings.KIS_IS_VIRTUAL else '실전투자'}")
    logger.info("=" * 60)

    # Agent 초기화
    agents = [ClaudeAgent(), GPTAgent(), GeminiAgent()]
    moderator = Moderator(agents)
    tracker   = PositionTracker()
    ws_client = KISWebSocket()

    stop_event = asyncio.Event()

    # 시그널 처리 (Ctrl+C)
    def _shutdown():
        logger.info("종료 신호 수신 — 시스템 종료 중...")
        stop_event.set()
        ws_client.stop()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown)

    # 구독할 종목 초기 스캔 (WebSocket 연결용)
    initial_candidates = scan_candidates()
    initial_codes = [c["stock_code"] for c in initial_candidates]

    async def _price_callback(data: dict) -> None:
        pass  # ws_client 내부 캐시에 저장됨

    # WebSocket & 매매 루프 동시 실행
    await asyncio.gather(
        ws_client.connect_and_subscribe(initial_codes, _price_callback),
        trading_loop(moderator, tracker, ws_client, stop_event),
    )

    logger.info("시스템 종료 완료")


if __name__ == "__main__":
    asyncio.run(main())
