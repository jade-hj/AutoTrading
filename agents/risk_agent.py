"""
Model B — Groq / Qwen3-32b  (리스크 관리 전문)

역할: 신호 Agent의 BUY/SELL 결정을 받아
      포지션 사이징, 손절가/익절가를 계산하고 OK/REJECT를 출력한다.

정량 기준:
  - 종목당 최대 투자 비중 : 총 자산의 20%
  - 동시 보유 종목 수     : 최대 3종목
  - 손절가               : 진입가 × (1 - 0.5%)
  - 1차 익절가           : 진입가 × (1 + 0.8%)  → 절반 매도
  - 2차 익절가           : 진입가 × (1 + 1.5%)  → 전량 매도
  - REJECT 조건          : 자금 부족, 최대 포지션 초과, 일일 손실 한도 도달
"""
import logging

from openai import AsyncOpenAI

from agents.base_agent import Action, ScalpingContext, SignalDecision, RiskDecision
from agents.claude_agent import _parse_json
from config import settings

logger = logging.getLogger(__name__)


class RiskAgent:
    """포지션 사이징 및 손절/익절가 계산 Agent (Qwen3-32b)."""

    def __init__(self):
        self._client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )

    def _system_prompt(self) -> str:
        return (
            "당신은 한국 주식 단타 매매 리스크 관리 전문가입니다.\n"
            "신호 Agent의 결정과 현재 포트폴리오 상태를 보고 "
            "주문 수량, 손절가, 익절가를 계산하여 주문 승인(approved) 여부를 결정합니다.\n\n"
            f"리스크 기준:\n"
            f"  - 종목당 최대 비중: {settings.SCALPING_POSITION_RATIO:.0%}\n"
            f"  - 최대 동시 보유: {settings.SCALPING_MAX_POSITIONS}종목\n"
            f"  - 손절: 진입가 대비 -{settings.SCALPING_STOP_LOSS:.1%}\n"
            f"  - 1차 익절: 진입가 대비 +{settings.SCALPING_TAKE_PROFIT_1:.1%}\n"
            f"  - 2차 익절: 진입가 대비 +{settings.SCALPING_TAKE_PROFIT_2:.1%}\n"
            "응답은 반드시 지정된 JSON 형식으로만 작성하세요."
        )

    async def _call(self, prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=settings.GROQ_MODEL_B,
            max_tokens=settings.MAX_TOKENS_PER_AGENT,
            temperature=0.2,
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {"role": "user",   "content": prompt},
            ],
        )
        return response.choices[0].message.content

    async def analyze(
        self,
        ctx: ScalpingContext,
        signal: SignalDecision,
    ) -> RiskDecision:
        # 사전 계산 (LLM 없이 확정 가능한 수치)
        price = ctx.current_price
        total = ctx.available_cash + sum(
            h["quantity"] * h["current_price"] for h in ctx.holdings
        )
        max_invest   = int(total * settings.SCALPING_POSITION_RATIO)
        max_quantity = max_invest // price if price > 0 else 0
        invest_cash  = min(max_invest, ctx.available_cash)
        calc_qty     = invest_cash // price if price > 0 else 0

        stop_loss_p = int(price * (1 - settings.SCALPING_STOP_LOSS))
        tp1_p       = int(price * (1 + settings.SCALPING_TAKE_PROFIT_1))
        tp2_p       = int(price * (1 + settings.SCALPING_TAKE_PROFIT_2))

        prompt = f"""
## 신호 Agent 결정
액션: {signal.action}  확신도: {signal.confidence:.0%}
근거: {signal.reasoning}

## 현재 포트폴리오 상태
예수금: {ctx.available_cash:,}원
총 자산: {total:,}원
현재 보유 종목 수: {ctx.holding_count} / {settings.SCALPING_MAX_POSITIONS}
{self._holdings_text(ctx.holdings)}

## 주문 대상
종목: {ctx.stock_code} {ctx.stock_name}
현재가: {price:,}원
계산된 최대 수량: {calc_qty}주 (투자 가능 현금 {invest_cash:,}원 기준)
손절가: {stop_loss_p:,}원 (진입가 -{settings.SCALPING_STOP_LOSS:.1%})
1차 익절가: {tp1_p:,}원 (진입가 +{settings.SCALPING_TAKE_PROFIT_1:.1%})
2차 익절가: {tp2_p:,}원 (진입가 +{settings.SCALPING_TAKE_PROFIT_2:.1%})

## 판단 요청
위 리스크 기준에 따라 주문 승인 여부를 결정하세요.
REJECT 사유: 자금 부족, 최대 포지션 초과, 리스크 대비 수익성 불충분

다음 JSON 형식으로만 응답하세요:
{{
  "approved": true | false,
  "quantity": 주문_수량(정수),
  "stop_loss_price": 손절가(정수),
  "take_profit_1_price": 1차_익절가(정수),
  "take_profit_2_price": 2차_익절가(정수),
  "reasoning": "승인/거부 근거 (2~3문장)"
}}
"""
        raw = await self._call(prompt)
        data = _parse_json(raw)

        decision = RiskDecision(
            approved            = bool(data.get("approved", False)),
            quantity            = int(data.get("quantity", calc_qty)),
            stop_loss_price     = int(data.get("stop_loss_price", stop_loss_p)),
            take_profit_1_price = int(data.get("take_profit_1_price", tp1_p)),
            take_profit_2_price = int(data.get("take_profit_2_price", tp2_p)),
            reasoning           = data.get("reasoning", ""),
        )

        # 수량 0이면 강제 REJECT
        if decision.quantity <= 0:
            decision.approved = False
            decision.reasoning = "주문 수량 0 — 자금 부족"

        logger.info("[RiskAgent] %s → %s 수량=%d 손절=%s 1차익절=%s",
                    ctx.stock_code,
                    "OK" if decision.approved else "REJECT",
                    decision.quantity,
                    f"{decision.stop_loss_price:,}",
                    f"{decision.take_profit_1_price:,}")
        return decision

    def _holdings_text(self, holdings: list[dict]) -> str:
        if not holdings:
            return "보유 종목 없음"
        lines = ["보유 종목:"]
        for h in holdings:
            lines.append(
                f"  [{h['stock_code']}] {h['stock_name']} "
                f"{h['quantity']}주 (손익: {h['profit_loss']:+.2f}%)"
            )
        return "\n".join(lines)
