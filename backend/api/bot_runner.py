"""
봇 실행 루프 — main.py 에서 분리해 API 서버에서도 호출 가능하게 만든 버전.

server.py (FastAPI) 와 main.py (CLI) 모두 이 함수를 사용한다.
"""
import asyncio
import logging
from datetime import datetime, time as dtime

from config import settings
from data.market_scanner import scan_candidates
from data.indicators import get_all_indicators
from agents.base_agent import Action, ScalpingContext
from kis import rest_client as kis
from utils.logger import trade_log

logger = logging.getLogger(__name__)

MARKET_OPEN  = dtime(9,  0)
MARKET_CLOSE = dtime(15, 30)


def _is_market_open() -> bool:
    now = datetime.now().time()
    return MARKET_OPEN <= now <= MARKET_CLOSE


def _build_context(candidate: dict, balance: dict, kospi_rate: float) -> ScalpingContext | None:
    code = candidate["stock_code"]
    try:
        candles = kis.get_minute_ohlcv(code, count=settings.SCALPING_CANDLE_COUNT)
    except Exception as e:
        logger.warning("[스캔] %s 분봉 조회 실패: %s", code, e)
        candles = []

    if len(candles) < 5:
        return None

    indicators = get_all_indicators(candles)

    # volume_ratio: market_scanner에서 계산한 오늘 거래량 / 20일 평균 거래량
    volume_ratio = candidate.get("volume_ratio", 1.0)

    return ScalpingContext(
        stock_code        = code,
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


def _sync_holdings_to_tracker(tracker, holdings: list[dict]) -> None:
    """KIS 잔고에 있지만 PositionTracker에 없는 포지션을 자동 등록한다.

    서버 재시작 후 기존 보유 종목을 손절/익절 모니터링에 포함시키기 위해 사용.
    매입가 기준으로 손절/익절가를 계산하며, 현재가가 이미 tp1 이상이면 tp1_hit=True로 설정한다.
    """
    tracked = set(tracker._positions.keys())
    for h in holdings:
        code = h["stock_code"]
        if code in tracked:
            continue
        avg_price   = int(h.get("avg_price", h.get("buy_price", h["current_price"])))
        current     = h["current_price"]
        qty         = h["quantity"]
        sl          = int(avg_price * (1 - settings.SCALPING_STOP_LOSS))
        tp1         = int(avg_price * (1 + settings.SCALPING_TAKE_PROFIT_1))
        tp2         = int(avg_price * (1 + settings.SCALPING_TAKE_PROFIT_2))
        tracker.register(
            stock_code          = code,
            stock_name          = h["stock_name"],
            quantity            = qty,
            entry_price         = avg_price,
            stop_loss_price     = sl,
            take_profit_1_price = tp1,
            take_profit_2_price = tp2,
        )
        # 현재가가 이미 1차 익절가 이상이면 tp1_hit=True 설정 (재시작 후 중복 실행 방지)
        if current >= tp1:
            tracker._positions[code]["tp1_hit"] = True
            logger.info("[sync] %s tp1_hit=True 설정 (현재가 %s원 ≥ tp1 %s원)",
                        code, f"{current:,}", f"{tp1:,}")
        logger.info("[sync] KIS잔고 → 트래커 등록: %s %s %d주 (매입가 %s원 | SL %s | TP1 %s | TP2 %s)",
                    code, h["stock_name"], qty,
                    f"{avg_price:,}", f"{sl:,}", f"{tp1:,}", f"{tp2:,}")


async def run_scanning_loop(coordinator, tracker, stop_event: asyncio.Event) -> None:
    """5분 스캔 루프 (API 서버 / CLI 공용)"""
    # bot_state 는 순환 import 방지를 위해 여기서 import
    from api.state import bot_state

    logger.info("단타 스캔 루프 시작 (주기: %d초)", settings.SCALPING_INTERVAL_SEC)
    while not stop_event.is_set():
        try:
            if not _is_market_open():
                logger.info("장 외 시간 — 대기")
                await asyncio.sleep(60)
                continue

            if tracker.is_daily_loss_limit_reached():
                logger.warning("일일 손실 한도 도달 — 당일 신규 진입 중지")
                await asyncio.sleep(60)
                continue

            balance    = kis.get_balance()
            kospi_rate = kis.get_kospi_change_rate()
            tracker.set_initial_cash(balance["available_cash"])

            # KIS 잔고에 있는 포지션을 트래커에 자동 동기화 (재시작 후 복원)
            if balance["holdings"]:
                _sync_holdings_to_tracker(tracker, balance["holdings"])

            logger.info(
                "스캔 시작 | 예수금: %s원 | 보유: %d종목 | 코스피: %+.2f%%",
                f"{balance['available_cash']:,}", len(balance["holdings"]), kospi_rate,
            )

            if len(balance["holdings"]) >= settings.SCALPING_MAX_POSITIONS:
                logger.info("최대 보유 종목 수 도달 (%d) — 스캔 스킵", settings.SCALPING_MAX_POSITIONS)
                await asyncio.sleep(settings.SCALPING_INTERVAL_SEC)
                continue

            loop = asyncio.get_event_loop()
            candidates = await loop.run_in_executor(None, scan_candidates)
            bot_state.last_scan_candidates = candidates
            bot_state.last_scan_time       = datetime.now()

            if not candidates:
                logger.warning("후보 종목 없음")
                await asyncio.sleep(settings.SCALPING_INTERVAL_SEC)
                continue

            for candidate in candidates:
                if stop_event.is_set():
                    break
                code = candidate["stock_code"]
                held_codes = {h["stock_code"] for h in balance["holdings"]}
                if code in held_codes:
                    continue
                # 당일 손절 종목 재매수 금지
                if code in bot_state.daily_blocked_codes:
                    logger.info("[스캔] %s 당일 손절 종목 — 재매수 금지 스킵", code)
                    continue

                ctx = _build_context(candidate, balance, kospi_rate)
                if ctx is None:
                    continue

                result = await coordinator.run(ctx)

                if result.executed and result.action == Action.BUY:
                    try:
                        order = kis.place_order(result.stock_code, "BUY", result.quantity, price=0)
                        trade_log.log_buy(
                            stock_code=result.stock_code, stock_name=result.stock_name,
                            buy_price=ctx.current_price, quantity=result.quantity,
                            signal_action=str(result.signal.action) if result.signal else "BUY",
                            signal_conf=result.signal.confidence if result.signal else 0.0,
                            signal_reason=result.signal.reasoning if result.signal else "",
                            risk_reason=result.risk.reasoning if result.risk else "",
                            stop_loss=result.stop_loss_price, tp1=result.take_profit_1_price,
                            tp2=result.take_profit_2_price,
                            market_reason=result.market.reasoning if result.market else "",
                            order_no=order["order_no"],
                        )
                        bot_state.record_buy(
                            stock_code=result.stock_code, stock_name=result.stock_name,
                            price=ctx.current_price, quantity=result.quantity,
                            order_no=order["order_no"],
                        )
                        tracker.register(
                            stock_code=result.stock_code, stock_name=result.stock_name,
                            quantity=result.quantity, entry_price=ctx.current_price,
                            stop_loss_price=result.stop_loss_price,
                            take_profit_1_price=result.take_profit_1_price,
                            take_profit_2_price=result.take_profit_2_price,
                        )
                        balance = kis.get_balance()
                        if len(balance["holdings"]) >= settings.SCALPING_MAX_POSITIONS:
                            break
                    except Exception as e:
                        logger.error("매수 주문 실패: %s — %s", result.stock_code, e)

        except Exception as e:
            logger.error("스캔 루프 오류: %s", e, exc_info=True)

        await asyncio.sleep(settings.SCALPING_INTERVAL_SEC)


async def run_monitor_loop(tracker, stop_event: asyncio.Event) -> None:
    """30초 포지션 모니터 루프"""
    await tracker.monitor_loop(stop_event)
