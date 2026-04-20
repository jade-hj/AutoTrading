"""
포지션 및 손익 추적

ScalpingPositionTracker: 단타용 — 30초마다 손절/1차익절/2차익절 자동 체크
PositionTracker        : 기존 호환용 — 잔고 조회 후 Portfolio 반환
"""
import asyncio
import logging

from kis import rest_client as kis
from trading.portfolio import Portfolio
from config import settings

logger = logging.getLogger(__name__)


# ── 기존 호환용 ───────────────────────────────────────────────

class PositionTracker:
    def __init__(self):
        self._last_balance: dict = {}

    def refresh(self) -> Portfolio:
        """잔고 조회 후 Portfolio 객체 반환"""
        balance = kis.get_balance()
        self._last_balance = balance
        self._log_positions(balance)
        return Portfolio(
            available_cash = balance["available_cash"],
            total_value    = balance["total_eval"],
            holdings       = balance["holdings"],
        )

    def _log_positions(self, balance: dict) -> None:
        logger.info(
            "잔고 현황 | 예수금: %s원 | 총평가: %s원",
            f"{balance['available_cash']:,}", f"{balance['total_eval']:,}",
        )
        for h in balance["holdings"]:
            logger.info(
                "  [%s] %s %d주 | 평균단가: %s원 | 손익률: %+.2f%%",
                h["stock_code"], h["stock_name"], h["quantity"],
                f"{h['avg_price']:,.0f}", h["profit_loss"],
            )

    @property
    def holdings(self) -> list[dict]:
        return self._last_balance.get("holdings", [])


# ── 단타 전용 포지션 모니터 ───────────────────────────────────

class ScalpingPositionTracker:
    """
    단타 보유 포지션의 손절/익절을 자동으로 감시하고 매도 주문을 실행한다.

    보유 종목별로 진입 시 등록한 stop_loss / take_profit_1 / take_profit_2 가격을
    기준으로 SCALPING_MONITOR_SEC 마다 현재가를 조회해 조건 충족 시 즉시 매도한다.
    """

    def __init__(self):
        # {stock_code: {"stop_loss": int, "tp1": int, "tp2": int, "tp1_hit": bool, "quantity": int}}
        self._positions: dict[str, dict] = {}
        self._daily_loss: float = 0.0   # 당일 실현 손익 합산 (원)
        self._initial_cash: int = 0     # 당일 시작 예수금 (손실 한도 계산 기준)

    def register(
        self,
        stock_code: str,
        stock_name: str,
        quantity: int,
        entry_price: int,
        stop_loss_price: int,
        take_profit_1_price: int,
        take_profit_2_price: int,
    ) -> None:
        """매수 체결 후 포지션 등록"""
        self._positions[stock_code] = {
            "stock_name":   stock_name,
            "quantity":     quantity,
            "entry_price":  entry_price,
            "stop_loss":    stop_loss_price,
            "tp1":          take_profit_1_price,
            "tp2":          take_profit_2_price,
            "tp1_hit":      False,   # 1차 익절 실행 여부
        }
        logger.info(
            "[PositionTracker] 등록: %s %s %d주 | 손절=%s 1차익절=%s 2차익절=%s",
            stock_code, stock_name, quantity,
            f"{stop_loss_price:,}", f"{take_profit_1_price:,}", f"{take_profit_2_price:,}",
        )

    def unregister(self, stock_code: str) -> None:
        self._positions.pop(stock_code, None)

    def set_initial_cash(self, cash: int) -> None:
        if self._initial_cash == 0:
            self._initial_cash = cash

    def is_daily_loss_limit_reached(self) -> bool:
        if self._initial_cash == 0:
            return False
        loss_rate = self._daily_loss / self._initial_cash
        return loss_rate <= -settings.SCALPING_DAILY_LOSS_LIMIT

    async def monitor_loop(self, stop_event: asyncio.Event) -> None:
        """SCALPING_MONITOR_SEC 마다 보유 포지션 손절/익절 체크"""
        logger.info("[PositionTracker] 모니터 루프 시작 (주기: %ds)", settings.SCALPING_MONITOR_SEC)
        while not stop_event.is_set():
            try:
                await self._check_positions()
            except Exception as e:
                logger.error("[PositionTracker] 모니터 오류: %s", e, exc_info=True)
            await asyncio.sleep(settings.SCALPING_MONITOR_SEC)

    async def _check_positions(self) -> None:
        if not self._positions:
            return

        codes = list(self._positions.keys())
        for code in codes:
            pos = self._positions.get(code)
            if pos is None:
                continue
            try:
                price_data = kis.get_current_price(code)
                current    = price_data["current_price"]
                await self._evaluate(code, pos, current)
            except Exception as e:
                logger.warning("[PositionTracker] %s 현재가 조회 실패: %s", code, e)

    async def _evaluate(self, code: str, pos: dict, current: int) -> None:
        qty  = pos["quantity"]
        name = pos["stock_name"]

        # ── 손절 ─────────────────────────────────────────────
        if current <= pos["stop_loss"]:
            logger.warning(
                "[PositionTracker] 손절 실행: %s %s | 현재가=%s 손절가=%s",
                code, name, f"{current:,}", f"{pos['stop_loss']:,}",
            )
            self._execute_sell(code, qty, reason="손절")
            self._record_pnl(pos["entry_price"], current, qty)
            return

        # ── 2차 익절 ─────────────────────────────────────────
        if current >= pos["tp2"]:
            logger.info(
                "[PositionTracker] 2차 익절 실행: %s %s | 현재가=%s 2차익절가=%s",
                code, name, f"{current:,}", f"{pos['tp2']:,}",
            )
            self._execute_sell(code, qty, reason="2차 익절")
            self._record_pnl(pos["entry_price"], current, qty)
            return

        # ── 1차 익절 (절반 매도) ─────────────────────────────
        if current >= pos["tp1"] and not pos["tp1_hit"]:
            half = max(1, qty // 2)
            logger.info(
                "[PositionTracker] 1차 익절 실행: %s %s %d주(절반) | 현재가=%s",
                code, name, half, f"{current:,}",
            )
            self._execute_sell(code, half, reason="1차 익절")
            self._record_pnl(pos["entry_price"], current, half)
            pos["quantity"]  -= half
            pos["tp1_hit"]    = True
            # 잔여 수량 0이면 포지션 제거
            if pos["quantity"] <= 0:
                self.unregister(code)

    def _execute_sell(self, code: str, qty: int, reason: str) -> None:
        try:
            order = kis.place_order(code, "SELL", qty, price=0)
            logger.info("[PositionTracker] 매도 완료: %s %d주 (%s) 주문번호=%s",
                        code, qty, reason, order["order_no"])
            self.unregister(code)
        except Exception as e:
            logger.error("[PositionTracker] 매도 실패: %s — %s", code, e)

    def _record_pnl(self, entry: int, exit_price: int, qty: int) -> None:
        pnl = (exit_price - entry) * qty
        self._daily_loss += pnl
        logger.info("[PositionTracker] 실현 손익: %+,d원 | 당일 누적: %+,d원",
                    pnl, int(self._daily_loss))
