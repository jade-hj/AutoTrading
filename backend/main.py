"""
주식 단타 자동매매 시스템 — 진입점

실행 흐름:
  ┌─────────────────────────────────────────────┐
  │  5분 스캔 루프                                │
  │  1. 장 시간 & 일일 손실 한도 체크             │
  │  2. 거래량 급증 후보 종목 스캔 (KOSPI Top 30) │
  │  3. 각 종목 분봉 + 지표 계산                  │
  │  4. 3개 Agent 병렬 분석 (AND 조건)            │
  │  5. 합의 시 주문 실행 + 포지션 등록           │
  └─────────────────────────────────────────────┘
  ┌─────────────────────────────────────────────┐
  │  30초 포지션 모니터 루프                      │
  │  보유 종목 손절 / 1차 익절 / 2차 익절 자동 실행│
  └─────────────────────────────────────────────┘
"""
import asyncio
import signal
import logging
from datetime import datetime, time as dtime

from config import settings
from data.market_scanner import scan_candidates
from data.indicators import get_all_indicators
from agents.base_agent import Action, ScalpingContext
from agents.scalping_coordinator import ScalpingCoordinator
from trading.position_tracker import ScalpingPositionTracker
from kis import rest_client as kis
from utils.logger import setup_logger, trade_log

def _print_market_status() -> None:
    """시스템 시작 시 시장 현황을 한 번 조회해 로그로 남긴다."""
    try:
        kospi      = kis.get_kospi_index()
        balance    = kis.get_balance()
        candidates = scan_candidates()
        trade_log.log_market_status(
            kospi      = kospi,
            balance    = balance,
            candidates = candidates,
            mode       = "모의투자" if settings.KIS_IS_VIRTUAL else "실전투자",
        )
    except Exception as e:
        logger.warning("시장 현황 조회 실패: %s", e)

setup_logger()
logger = logging.getLogger(__name__)

MARKET_OPEN  = dtime(9,  0)
MARKET_CLOSE = dtime(15, 30)


def is_market_open() -> bool:
    now = datetime.now().time()
    return MARKET_OPEN <= now <= MARKET_CLOSE


def _build_context(candidate: dict, balance: dict, kospi_rate: float) -> ScalpingContext | None:
    """후보 종목 1개에 대한 ScalpingContext 생성. 실패 시 None 반환."""
    code = candidate["stock_code"]
    try:
        candles = kis.get_minute_ohlcv(code, count=settings.SCALPING_CANDLE_COUNT)
    except Exception as e:
        logger.warning("[스캔] %s 분봉 조회 실패: %s", code, e)
        candles = []

    if len(candles) < 5:
        logger.debug("[스캔] %s 분봉 데이터 부족 (%d개)", code, len(candles))
        return None

    indicators = get_all_indicators(candles)

    # 거래량 배수 — 최근 5분 평균 ÷ 직전 20분 평균 (지금 급증 중인지 감지)
    volumes = [c["volume"] for c in candles if c["volume"] > 0]
    if len(volumes) >= 10:
        recent  = volumes[-5:]          # 최근 5분
        prior   = volumes[-25:-5]       # 직전 20분 (없으면 그 이전 전체)
        if not prior:
            prior = volumes[:-5]
        avg_recent = sum(recent) / len(recent) if recent else 1
        avg_prior  = sum(prior)  / len(prior)  if prior  else 1
        volume_ratio = avg_recent / avg_prior if avg_prior > 0 else 1.0
    else:
        # 데이터 부족 시 단순 비교 (최신 ÷ 이전 평균)
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


# ── 스캔 루프 ─────────────────────────────────────────────────

async def scanning_loop(
    coordinator: ScalpingCoordinator,
    tracker: ScalpingPositionTracker,
    stop_event: asyncio.Event,
) -> None:
    logger.info("단타 스캔 루프 시작 (주기: %d초)", settings.SCALPING_INTERVAL_SEC)

    while not stop_event.is_set():
        try:
            if not is_market_open():
                logger.info("장 외 시간 — 대기")
                await asyncio.sleep(60)
                continue

            # 일일 손실 한도 체크
            if tracker.is_daily_loss_limit_reached():
                logger.warning("일일 손실 한도 도달 — 당일 신규 진입 중지")
                await asyncio.sleep(60)
                continue

            # 잔고 조회
            balance     = kis.get_balance()
            kospi_rate  = kis.get_kospi_change_rate()
            tracker.set_initial_cash(balance["available_cash"])

            logger.info(
                "스캔 시작 | 예수금: %s원 | 보유: %d종목 | 코스피: %+.2f%%",
                f"{balance['available_cash']:,}", len(balance["holdings"]), kospi_rate,
            )

            # 최대 보유 종목 수 초과 시 신규 진입 스킵
            if len(balance["holdings"]) >= settings.SCALPING_MAX_POSITIONS:
                logger.info("최대 보유 종목 수 도달 (%d) — 스캔 스킵", settings.SCALPING_MAX_POSITIONS)
                await asyncio.sleep(settings.SCALPING_INTERVAL_SEC)
                continue

            # 후보 종목 스캔 (거래량 상위)
            candidates = scan_candidates()
            if not candidates:
                logger.warning("후보 종목 없음")
                await asyncio.sleep(settings.SCALPING_INTERVAL_SEC)
                continue

            # 후보 종목별 AI 분석 (순차 처리 — API rate limit 고려)
            for candidate in candidates:
                if stop_event.is_set():
                    break

                # 이미 보유 중인 종목은 스킵
                held_codes = {h["stock_code"] for h in balance["holdings"]}
                if candidate["stock_code"] in held_codes:
                    continue

                ctx = _build_context(candidate, balance, kospi_rate)
                if ctx is None:
                    continue

                result = await coordinator.run(ctx)

                # 실행 가능한 결정이 나온 경우 주문
                if result.executed and result.action == Action.BUY:
                    try:
                        order = kis.place_order(
                            result.stock_code, "BUY", result.quantity, price=0
                        )
                        # 구조화 매수 로그 (콘솔 + 파일)
                        trade_log.log_buy(
                            stock_code    = result.stock_code,
                            stock_name    = result.stock_name,
                            buy_price     = ctx.current_price,
                            quantity      = result.quantity,
                            signal_action = str(result.signal.action) if result.signal else "BUY",
                            signal_conf   = result.signal.confidence if result.signal else 0.0,
                            signal_reason = result.signal.reasoning if result.signal else "",
                            risk_reason   = result.risk.reasoning if result.risk else "",
                            stop_loss     = result.stop_loss_price,
                            tp1           = result.take_profit_1_price,
                            tp2           = result.take_profit_2_price,
                            market_reason = result.market.reasoning if result.market else "",
                            order_no      = order["order_no"],
                        )
                        tracker.register(
                            stock_code          = result.stock_code,
                            stock_name          = result.stock_name,
                            quantity            = result.quantity,
                            entry_price         = ctx.current_price,
                            stop_loss_price     = result.stop_loss_price,
                            take_profit_1_price = result.take_profit_1_price,
                            take_profit_2_price = result.take_profit_2_price,
                        )
                        # 매수 후 잔고 갱신 & 최대 포지션 도달 시 스캔 중단
                        balance = kis.get_balance()
                        if len(balance["holdings"]) >= settings.SCALPING_MAX_POSITIONS:
                            break
                    except Exception as e:
                        logger.error("매수 주문 실패: %s — %s", result.stock_code, e)

                elif result.executed and result.action == Action.SELL:
                    held = next(
                        (h for h in balance["holdings"]
                         if h["stock_code"] == result.stock_code), None
                    )
                    if held:
                        try:
                            order = kis.place_order(
                                result.stock_code, "SELL", held["quantity"], price=0
                            )
                            # 구조화 매도 로그 (콘솔 + 파일)
                            trade_log.log_sell(
                                stock_code  = result.stock_code,
                                stock_name  = result.stock_name,
                                sell_price  = ctx.current_price,
                                quantity    = held["quantity"],
                                entry_price = int(held.get("avg_price", ctx.current_price)),
                                reason      = f"AI 신호 매도 — {result.signal.reasoning[:60] if result.signal else ''}",
                                order_no    = order["order_no"],
                            )
                            tracker.unregister(result.stock_code)
                        except Exception as e:
                            logger.error("매도 주문 실패: %s — %s", result.stock_code, e)

        except Exception as e:
            logger.error("스캔 루프 오류: %s", e, exc_info=True)

        await asyncio.sleep(settings.SCALPING_INTERVAL_SEC)


# ── 메인 ─────────────────────────────────────────────────────

async def main() -> None:
    logger.info("=" * 60)
    logger.info("단타 자동매매 시스템 시작")
    logger.info("모드: %s", "모의투자" if settings.KIS_IS_VIRTUAL else "실전투자")
    logger.info("손절: -%s%% | 1차익절: +%s%% | 2차익절: +%s%%",
                f"{settings.SCALPING_STOP_LOSS*100:.1f}",
                f"{settings.SCALPING_TAKE_PROFIT_1*100:.1f}",
                f"{settings.SCALPING_TAKE_PROFIT_2*100:.1f}")
    logger.info("스캔 주기: %d초 | 포지션 모니터: %d초",
                settings.SCALPING_INTERVAL_SEC, settings.SCALPING_MONITOR_SEC)
    logger.info("=" * 60)

    # 시장 현황 1회 출력 (시작 시)
    _print_market_status()

    coordinator = ScalpingCoordinator()
    tracker     = ScalpingPositionTracker()
    stop_event  = asyncio.Event()

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            pass  # Windows에서는 SIGTERM 미지원

    await asyncio.gather(
        scanning_loop(coordinator, tracker, stop_event),
        tracker.monitor_loop(stop_event),
    )

    logger.info("시스템 종료 완료")


if __name__ == "__main__":
    asyncio.run(main())
