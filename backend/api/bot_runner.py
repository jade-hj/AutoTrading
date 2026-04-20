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

    volumes = [c["volume"] for c in candles if c["volume"] > 0]
    if len(volumes) >= 10:
        recent = volumes[-5:]
        prior  = volumes[-25:-5]
        if not prior:
            prior = volumes[:-5]
        avg_recent = sum(recent) / len(recent) if recent else 1
        avg_prior  = sum(prior)  / len(prior)  if prior  else 1
        volume_ratio = avg_recent / avg_prior if avg_prior > 0 else 1.0
    else:
        avg_vol = sum(volumes[:-1]) / len(volumes[:-1]) if len(volumes) > 1 else 1
        volume_ratio = volumes[-1] / avg_vol if avg_vol > 0 else 1.0

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
                held_codes = {h["stock_code"] for h in balance["holdings"]}
                if candidate["stock_code"] in held_codes:
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
