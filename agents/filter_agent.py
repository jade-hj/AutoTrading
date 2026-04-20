"""
Model C — Groq / Llama-3.1-8b  (시장 필터 전문)

역할: 시장 전체 상황을 빠르게 판단해 진입 허가(GO) / 금지(NO-GO)를 출력한다.
      가장 빠른 모델을 사용해 실시간 필터 역할을 수행한다.

정량 기준:
  - 거래 시간  : 09:30 이전 또는 14:50 이후 → NO-GO
  - 코스피 범위: 전일 대비 ±0.3% 이내       → NO-GO (방향 불명확)
  - 갭 필터    : 시가 갭 ±2% 초과 종목      → NO-GO (추격 리스크)
  - 등락률     : +25% 이상 (상한가 근접)     → NO-GO
"""
import logging
from datetime import datetime

from openai import AsyncOpenAI

from agents.base_agent import ScalpingContext, MarketDecision
from agents.claude_agent import _parse_json
from config import settings

logger = logging.getLogger(__name__)


class FilterAgent:
    """시장 상황 필터 Agent (Llama-3.1-8b)."""

    def __init__(self):
        self._client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )

    def _system_prompt(self) -> str:
        return (
            "당신은 한국 주식 단타 매매 시장 상황 분석 전문가입니다.\n"
            "현재 시장 환경이 단타 진입에 적합한지 판단하여 GO 또는 NO-GO를 결정합니다.\n"
            "응답은 반드시 지정된 JSON 형식으로만 작성하세요."
        )

    async def _call(self, prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=settings.GROQ_MODEL_C,
            max_tokens=600,
            temperature=0.2,
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {"role": "user",   "content": prompt},
            ],
        )
        return response.choices[0].message.content

    def _check_rules(self, ctx: ScalpingContext) -> tuple[bool, str]:
        """규칙 기반 사전 필터 (LLM 호출 전 빠른 체크)."""
        now = datetime.now()
        time_str = now.strftime("%H:%M")

        # 거래 시간 필터
        if time_str < settings.SCALPING_EXEC_START:
            return False, f"거래 시간 전 ({time_str} < {settings.SCALPING_EXEC_START})"
        if time_str > settings.SCALPING_EXEC_END:
            return False, f"거래 시간 종료 ({time_str} > {settings.SCALPING_EXEC_END})"

        # 코스피 방향 불명확
        if abs(ctx.kospi_change_rate) <= settings.SCALPING_KOSPI_RANGE * 100:
            return False, f"코스피 방향 불명확 ({ctx.kospi_change_rate:+.2f}%)"

        # 갭 필터 — 시가가 전일 종가 대비 너무 크게 벌어진 경우
        if ctx.open_price > 0 and ctx.minute_candles:
            prev_close = ctx.minute_candles[0].get("close", ctx.open_price)
            if prev_close > 0:
                gap = abs(ctx.open_price - prev_close) / prev_close
                if gap >= settings.SCALPING_GAP_LIMIT:
                    return False, f"갭 과대 ({gap:.1%} ≥ {settings.SCALPING_GAP_LIMIT:.0%})"

        # 상한가 근접
        if ctx.change_rate >= 25.0:
            return False, f"상한가 근접 ({ctx.change_rate:+.2f}%)"

        return True, "사전 규칙 통과"

    async def analyze(self, ctx: ScalpingContext) -> MarketDecision:
        # 규칙 기반 사전 필터 (빠른 판단)
        rule_pass, rule_reason = self._check_rules(ctx)
        if not rule_pass:
            logger.info("[FilterAgent] %s → NO-GO (%s)", ctx.stock_code, rule_reason)
            return MarketDecision(go=False, confidence=1.0, reasoning=rule_reason)

        # LLM 최종 판단
        prompt = f"""
## 현재 시장 상황
코스피 등락률: {ctx.kospi_change_rate:+.2f}%
현재 시각: {datetime.now().strftime('%H:%M')}

## 분석 종목
종목: {ctx.stock_code} {ctx.stock_name}
현재가: {ctx.current_price:,}원  등락률: {ctx.change_rate:+.2f}%
거래량 배수: {ctx.volume_ratio:.1f}x

## 사전 규칙 체크 결과: 통과

## 판단 요청
시장 전체 방향성과 종목 수급 측면에서 지금 진입이 적합한지 판단하세요.

다음 JSON 형식으로만 응답하세요:
{{
  "go": true | false,
  "confidence": 0.0~1.0,
  "reasoning": "시장 상황 판단 근거 (1~2문장)"
}}
"""
        raw = await self._call(prompt)
        data = _parse_json(raw)

        decision = MarketDecision(
            go         = bool(data.get("go", False)),
            confidence = float(data.get("confidence", 0.5)),
            reasoning  = data.get("reasoning", rule_reason),
        )
        logger.info("[FilterAgent] %s → %s (확신도: %.0f%%) %s",
                    ctx.stock_code,
                    "GO" if decision.go else "NO-GO",
                    decision.confidence * 100,
                    decision.reasoning[:60])
        return decision
