"""
Model A — Groq / Llama-3.3-70b  (신호 탐지 전문)

역할: FilterAgent 통과 후 5분봉 기술적 지표(RSI·MACD·MA·볼린저밴드·거래량)를 분석해
      BUY / SELL / HOLD 신호와 목표가를 출력한다.
      AND 조건 파이프라인의 두 번째 관문.

────────────────────────────────────────────────────────────
오전 모드 (09:30~11:59) — 거래량 급등 초기 포착
────────────────────────────────────────────────────────────
  BUY 조건: 아래 4개 중 3개 이상 충족
    1. RSI 50~70 구간
    2. MACD 골든크로스 또는 히스토그램 양수
    3. MA5 > MA20 (상승 정배열)
    4. 거래량 배수 1.5x 이상
  SELL: RSI > 75 또는 볼린저밴드 상단 돌파 (과열)
  HOLD: 조건 2개 이하 충족

────────────────────────────────────────────────────────────
오후 모드 (12:00~14:50) — 눌림목 반등 / 오후 새 테마 포착
────────────────────────────────────────────────────────────
  BUY 조건: 아래 4개 중 2개 이상 충족 (오전보다 완화)
    1. RSI 40~70 구간 (하한 완화: 50→40)
    2. MACD 히스토그램 양수 또는 골든크로스
    3. MA5 > MA20 또는 볼린저밴드 %B > 0.5 (OR 조건으로 완화)
    4. 거래량 배수 0.8x 이상 (하한 완화: 1.5→0.8)
  SELL: RSI > 75 또는 볼린저밴드 상단 돌파 (과열)
  HOLD: 전반적 하락 흐름이거나 조건 1개 이하 충족
  ※ 오후는 눌림목 반등 특성상 거래량·RSI 기준을 낮춰 기회를 더 포착

설정값은 config/settings.py 의 SCALPING_AM_* / SCALPING_PM_* 로 관리한다.
"""
import json
import logging

from openai import AsyncOpenAI

from agents.base_agent import Action, ScalpingContext, SignalDecision
from agents.claude_agent import _parse_json
from agents.filter_agent import _get_session
from config import settings

logger = logging.getLogger(__name__)


class SignalAgent:
    """5분봉 기술적 분석으로 진입 신호를 생성한다 (Llama-3.3-70b)."""

    def __init__(self):
        self._client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )

    def _system_prompt(self, session: str) -> str:
        if session == "AM":
            return (
                "당신은 한국 주식 단타 매매 전문가입니다.\n"
                "오전 장(09:30~11:59) 기준으로 5분봉 기술적 지표를 분석하여 "
                "매수(BUY), 매도(SELL), 보류(HOLD) 신호를 결정합니다.\n\n"
                "오전 BUY 기준 — 아래 4개 중 3개 이상 충족 시 BUY:\n"
                "  1. RSI 50~70 구간\n"
                "  2. MACD 골든크로스 또는 히스토그램 양수\n"
                "  3. MA5 > MA20 (상승 정배열)\n"
                "  4. 거래량 배수 1.5x 이상\n"
                "  SELL: RSI>75 또는 볼린저밴드 상단 돌파 시 과열 판단\n"
                "  HOLD: 위 조건 2개 이하 충족\n"
                "응답은 반드시 지정된 JSON 형식으로만 작성하세요."
            )
        else:
            return (
                "당신은 한국 주식 단타 매매 전문가입니다.\n"
                "오후 장(12:00~14:50) 기준으로 5분봉 기술적 지표를 분석하여 "
                "매수(BUY), 매도(SELL), 보류(HOLD) 신호를 결정합니다.\n\n"
                "오후 BUY 기준 — 아래 4개 중 2개 이상 충족 + 전반적 상승 흐름 판단 시 BUY:\n"
                "  1. RSI 40~70 구간\n"
                "  2. MACD 히스토그램 양수(상승 전환) 또는 골든크로스\n"
                "  3. MA5 > MA20 또는 볼린저밴드 중간선 상향돌파(%B > 0.5)\n"
                "  4. 거래량 배수 0.8x 이상\n"
                "  SELL: RSI>75 또는 볼린저밴드 상단 돌파 시 과열 판단\n"
                "  HOLD: 전반적 하락 흐름이거나 조건 1개 이하 충족\n"
                "응답은 반드시 지정된 JSON 형식으로만 작성하세요."
            )

    async def _call(self, prompt: str, session: str) -> str:
        response = await self._client.chat.completions.create(
            model=settings.GROQ_MODEL_A,
            max_tokens=settings.MAX_TOKENS_PER_AGENT,
            temperature=0.3,
            messages=[
                {"role": "system", "content": self._system_prompt(session)},
                {"role": "user",   "content": prompt},
            ],
        )
        return response.choices[0].message.content

    async def analyze(self, ctx: ScalpingContext) -> SignalDecision:
        session = _get_session()
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

        # 세션별 진입 기준 체크값
        rsi_val      = ind.get("rsi", 0) or 0
        hist_val     = macd.get("histogram") or 0
        bb_pct       = bb.get("percent_b") or 0
        ma5_val      = ma.get("ma5") or 0
        ma20_val     = ma.get("ma20") or 0

        if session == "AM":
            c1 = settings.SCALPING_AM_RSI_MIN <= rsi_val <= settings.SCALPING_AM_RSI_MAX
            c2 = macd.get("crossover", False) or hist_val > 0
            c3 = ma5_val > ma20_val
            c4 = ctx.volume_ratio >= settings.SCALPING_AM_VOLUME_SURGE
            met = sum([c1, c2, c3, c4])
            session_label = "오전"
            criteria_note = (
                f"- [{'O' if c1 else 'X'}] RSI 50~70 구간: {rsi_val:.1f}\n"
                f"- [{'O' if c2 else 'X'}] MACD 골든크로스 or 히스토그램 양수: {macd.get('crossover', False)} / {hist_val:.2f}\n"
                f"- [{'O' if c3 else 'X'}] MA 정배열(MA5>MA20): {ma5_val} > {ma20_val}\n"
                f"- [{'O' if c4 else 'X'}] 거래량 배수(≥1.5x): {ctx.volume_ratio:.1f}x\n"
                f"→ {met}/4 충족 (3개 이상이면 BUY 가능)"
            )
        else:
            c1 = settings.SCALPING_PM_RSI_MIN <= rsi_val <= settings.SCALPING_PM_RSI_MAX
            c2 = hist_val > 0 or macd.get("crossover", False)
            c3 = ma5_val > ma20_val or bb_pct > 0.5
            c4 = ctx.volume_ratio >= settings.SCALPING_PM_VOLUME_SURGE
            met = sum([c1, c2, c3, c4])
            session_label = "오후"
            criteria_note = (
                f"- [{'O' if c1 else 'X'}] RSI 40~70 구간: {rsi_val:.1f}\n"
                f"- [{'O' if c2 else 'X'}] MACD 히스토그램 양수 or 골든크로스: {hist_val:.2f} / {macd.get('crossover', False)}\n"
                f"- [{'O' if c3 else 'X'}] MA정배열(MA5>MA20) or %B>0.5: {ma5_val}>{ma20_val} / %B={bb_pct:.2f}\n"
                f"- [{'O' if c4 else 'X'}] 거래량 배수(≥0.8x): {ctx.volume_ratio:.1f}x\n"
                f"→ {met}/4 충족 (2개 이상이면 BUY 가능)"
            )

        prompt = f"""
## 분석 종목 [{session_label} 모드]
코드: {ctx.stock_code}  종목명: {ctx.stock_name}
현재가: {ctx.current_price:,}원  등락률: {ctx.change_rate:+.2f}%
거래량 배수: {ctx.volume_ratio:.1f}x

## 기술적 지표 (분봉 기준)
RSI       : {ind.get('rsi', 'N/A')}
MACD      : {macd.get('macd', 'N/A')}  시그널: {macd.get('signal', 'N/A')}
히스토그램 : {macd.get('histogram', 'N/A')}  골든크로스: {macd.get('crossover', False)}
MA5       : {ma.get('ma5', 'N/A')}  MA20: {ma.get('ma20', 'N/A')}
정배열    : {ma.get('uptrend', False)}
볼린저밴드: 상단={bb.get('upper', 'N/A')}  중간={bb.get('middle', 'N/A')}  %B={bb.get('percent_b', 'N/A')}

## 최근 5개 분봉
{candle_lines}

## {session_label} 진입 기준 체크
{criteria_note}

위 데이터를 분석하여 다음 JSON 형식으로만 응답하세요:
{{
  "action": "BUY" | "SELL" | "HOLD",
  "confidence": 0.0~1.0,
  "target_price": 목표가(정수, HOLD이면 0),
  "reasoning": "판단 근거 (기술적 지표 중심, 2~3문장)"
}}
"""
        raw = await self._call(prompt, session)
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
