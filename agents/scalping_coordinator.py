"""
단타 합의 코디네이터

3개 Agent를 병렬 실행하고 AND 조건으로 최종 결정을 내린다.

실행 조건 (모두 충족해야 주문):
  - Model A (SignalAgent) : action == BUY 또는 SELL
  - Model B (RiskAgent)   : approved == True
  - Model C (FilterAgent) : go == True
"""
import asyncio
import logging

from agents.base_agent import Action, ScalpingContext, ScalpingResult
from agents.signal_agent import SignalAgent
from agents.risk_agent import RiskAgent
from agents.filter_agent import FilterAgent

logger = logging.getLogger(__name__)


class ScalpingCoordinator:
    """3개 Agent 병렬 실행 및 AND 조건 합의."""

    def __init__(self):
        self.signal_agent = SignalAgent()
        self.risk_agent   = RiskAgent()
        self.filter_agent = FilterAgent()

    async def run(self, ctx: ScalpingContext) -> ScalpingResult:
        """
        1. FilterAgent를 먼저 실행해 시장 상황이 나쁘면 빠르게 NO-GO 처리
        2. FilterAgent 통과 시 SignalAgent + RiskAgent 병렬 실행
        3. AND 조건 평가 후 ScalpingResult 반환
        """
        logger.info("[Coordinator] 분석 시작: %s %s @ %s원",
                    ctx.stock_code, ctx.stock_name, f"{ctx.current_price:,}")

        # ── Step 1: 시장 필터 (가장 빠른 모델로 선제 차단) ──────────
        market = await self.filter_agent.analyze(ctx)
        if not market.go:
            logger.info("[Coordinator] %s → NO-GO (시장 필터 차단): %s",
                        ctx.stock_code, market.reasoning)
            return ScalpingResult(
                stock_code=ctx.stock_code, stock_name=ctx.stock_name,
                action=Action.HOLD, quantity=0,
                stop_loss_price=0, take_profit_1_price=0, take_profit_2_price=0,
                executed=False, reason=f"NO-GO: {market.reasoning}",
                signal=None, risk=None, market=market,
            )

        # ── Step 2: 신호 탐지 + 리스크 관리 병렬 실행 ───────────────
        signal_task = asyncio.create_task(self.signal_agent.analyze(ctx))
        # RiskAgent는 signal 결과가 필요하므로 signal 완료 후 실행
        signal = await signal_task

        # 신호가 HOLD면 RiskAgent 호출 불필요
        if signal.action == Action.HOLD:
            logger.info("[Coordinator] %s → HOLD (신호 없음)", ctx.stock_code)
            return ScalpingResult(
                stock_code=ctx.stock_code, stock_name=ctx.stock_name,
                action=Action.HOLD, quantity=0,
                stop_loss_price=0, take_profit_1_price=0, take_profit_2_price=0,
                executed=False, reason="HOLD: 신호 없음",
                signal=signal, risk=None, market=market,
            )

        risk = await self.risk_agent.analyze(ctx, signal)

        # ── Step 3: AND 조건 평가 ────────────────────────────────────
        # signal.action != HOLD ✓ (위에서 이미 체크)
        # risk.approved
        # market.go ✓ (위에서 이미 체크)

        if not risk.approved:
            logger.info("[Coordinator] %s → REJECT (리스크 거부): %s",
                        ctx.stock_code, risk.reasoning)
            return ScalpingResult(
                stock_code=ctx.stock_code, stock_name=ctx.stock_name,
                action=Action.HOLD, quantity=0,
                stop_loss_price=0, take_profit_1_price=0, take_profit_2_price=0,
                executed=False, reason=f"REJECT: {risk.reasoning}",
                signal=signal, risk=risk, market=market,
            )

        # ── 최종 실행 결정 ───────────────────────────────────────────
        logger.info(
            "[Coordinator] %s → ✅ %s %d주 | 손절:%s 1차익절:%s 2차익절:%s",
            ctx.stock_code, signal.action, risk.quantity,
            f"{risk.stop_loss_price:,}", f"{risk.take_profit_1_price:,}",
            f"{risk.take_profit_2_price:,}",
        )
        return ScalpingResult(
            stock_code          = ctx.stock_code,
            stock_name          = ctx.stock_name,
            action              = signal.action,
            quantity            = risk.quantity,
            stop_loss_price     = risk.stop_loss_price,
            take_profit_1_price = risk.take_profit_1_price,
            take_profit_2_price = risk.take_profit_2_price,
            executed            = True,
            reason              = (
                f"Signal={signal.action}({signal.confidence:.0%}) | "
                f"Risk=OK({risk.quantity}주) | Market=GO"
            ),
            signal = signal,
            risk   = risk,
            market = market,
        )
