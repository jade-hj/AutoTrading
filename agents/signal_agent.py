"""
Model A — Groq / Llama-3.3-70b  (신호 탐지 전문)

역할: 5분봉 기술적 지표(RSI·MACD·MA·볼린저밴드·거래량) 분석 후
      BUY / SELL / HOLD 신호와 목표가를 출력한다.

정량 기준:
  - 거래량 급증: 전일 동시간대 대비 300% 이상
  - RSI        : 50~70 구간
  - MACD       : 히스토그램 양전환 (골든크로스)
  - MA 배열    : MA5 > MA20 (상승 정배열)
  - 볼린저밴드 : 중간 밴드 상향 돌파 (%B > 0.5)
"""
import json
import logging

from openai import AsyncOpenAI

from agents.base_agent import Action, ScalpingContext, SignalDecision
from agents.claude_agent import _parse_json
from config import settings

logger = logging.getLogger(__name__)


class SignalAgent:
    """5분봉 기술적 분석으로 진입 신호를 생성한다 (Llama-3.3-70b)."""

    def __init__(self):
        self._client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )

    def _system_prompt(self) -> str:
        return (
            "당신은 한국 주식 단타 매매 전문가입니다.\n"
            "5분봉 기술적 지표(RSI, MACD, 이동평균, 볼린저밴드, 거래량)를 분석하여 "
            "매수(BUY), 매도(SELL), 보류(HOLD) 신호를 결정합니다.\n\n"
            "진입 기준:\n"
            "  BUY : RSI 50~70 + MACD 골든크로스 + MA5>MA20 + 거래량 급증(300%↑)\n"
            "  SELL: 보유 종목에서 RSI>75 또는 볼린저밴드 상단 돌파 시 과열 판단\n"
            "  HOLD: 위 조건 미충족\n"
            "응답은 반드시 지정된 JSON 형식으로만 작성하세요."
        )

    async def _call(self, prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=settings.GROQ_MODEL_A,
            max_tokens=settings.MAX_TOKENS_PER_AGENT,
            temperature=0.3,
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {"role": "user",   "content": prompt},
            ],
        )
        return response.choices[0].message.content

    async def analyze(self, ctx: ScalpingContext) -> SignalDecision:
        ind = ctx.indicators
        ma  = ind.get("ma", {})
        macd = ind.get("macd", {})
        bb   = ind.get("bollinger", {})

        # 최근 5개 분봉 요약 (컨텍스트 절약)
        recent = ctx.minute_candles[-5:] if len(ctx.minute_candles) >= 5 else ctx.minute_candles
        candle_lines = "\n".join(
            f"  {c['date']}: O={c['open']:,} H={c['high']:,} L={c['low']:,} "
            f"C={c['close']:,} V={c['volume']:,}"
            for c in recent
        )

        prompt = f"""
## 분석 종목
코드: {ctx.stock_code}  종목명: {ctx.stock_name}
현재가: {ctx.current_price:,}원  등락률: {ctx.change_rate:+.2f}%
거래량 배수: {ctx.volume_ratio:.1f}x (전일 동시간대 대비)

## 기술적 지표 (분봉 기준)
RSI       : {ind.get('rsi', 'N/A')}
MACD      : {macd.get('macd', 'N/A')}  시그널: {macd.get('signal', 'N/A')}
히스토그램 : {macd.get('histogram', 'N/A')}  골든크로스: {macd.get('crossover', False)}
MA5       : {ma.get('ma5', 'N/A')}  MA20: {ma.get('ma20', 'N/A')}
정배열    : {ma.get('uptrend', False)}
볼린저밴드: 상단={bb.get('upper', 'N/A')}  중간={bb.get('middle', 'N/A')}  %B={bb.get('percent_b', 'N/A')}

## 최근 5개 분봉
{candle_lines}

## 진입 기준 체크
- 거래량 급증(300%↑): {ctx.volume_ratio >= 3.0}
- RSI 50~70 구간: {50 <= ind.get('rsi', 0) <= 70}
- MACD 골든크로스: {macd.get('crossover', False)}
- MA 정배열(MA5>MA20): {(ma.get('ma5') or 0) > (ma.get('ma20') or 0)}

위 데이터를 분석하여 다음 JSON 형식으로만 응답하세요:
{{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0~1.0,
  "target_price": 목표가(정수, HOLD이면 0),
  "reasoning": "판단 근거 (기술적 지표 중심, 2~3문장)"
}}
"""
        raw = await self._call(prompt)
        data = _parse_json(raw)

        action_str = data.get("action", "HOLD")
        try:
            action = Action(action_str)
        except ValueError:
            action = Action.HOLD

        decision = SignalDecision(
            action       = action,
            confidence   = float(data.get("confidence", 0.5)),
            target_price = int(data.get("target_price", 0)),
            reasoning    = data.get("reasoning", ""),
        )
        logger.info("[SignalAgent] %s → %s (확신도: %.0f%%) %s",
                    ctx.stock_code, decision.action, decision.confidence * 100,
                    decision.reasoning[:60])
        return decision
