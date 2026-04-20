"""
Model C — Groq / Llama-3.1-8b  (시장 필터 전문)

역할: 시장 전체 상황을 빠르게 판단해 진입 허가(GO) / 금지(NO-GO)를 출력한다.
      AND 조건 파이프라인의 첫 번째 관문으로, 가장 빠른 모델을 사용해
      조건 미충족 종목을 선제 차단 → 이후 SignalAgent·RiskAgent 호출을 최소화한다.

판단 방식:
  1단계: 규칙 기반 사전 필터 (_check_rules) — LLM 없이 즉시 NO-GO 결정
  2단계: 1단계 통과 시 LLM 최종 판단 — 시장 흐름·수급 측면 종합 평가

────────────────────────────────────────────────────────────
오전 모드 (09:30~11:59) — 거래량 급등 초기 포착 전략
────────────────────────────────────────────────────────────
  - 코스피 범위: 전일 대비 ±0.3% 이내       → NO-GO (방향 불명확)
  - 갭 필터    : 시가 갭 ±2% 초과 종목      → NO-GO (추격 리스크)
  - 등락률     : +25% 이상 (상한가 근접)     → NO-GO
  - 거래량 배수: 3.0x 미만                   → NO-GO
  ※ 오전은 거래량 폭발이 핵심 — 기준이 엄격함

────────────────────────────────────────────────────────────
오후 모드 (12:00~14:50) — 눌림목 반등 / 오후 새 테마 포착 전략
────────────────────────────────────────────────────────────
  - 코스피 범위: 전일 대비 ±0.3% 이내       → NO-GO (방향 불명확)
  - 갭 필터    : 시가 갭 ±5% 초과 종목      → NO-GO (오전보다 완화)
  - 등락률     : +0.5% 미만 또는 +20% 초과  → NO-GO (최소 모멘텀 & 상한가 근접만 제외)
  - 거래량 배수: 0.8x 미만                   → NO-GO (오전보다 완화)
  ※ 오후는 눌림목·신규 테마 대응 — 기준을 완화하여 기회 포착

설정값은 config/settings.py 의 SCALPING_AM_* / SCALPING_PM_* 로 관리한다.
"""
import logging
from datetime import datetime

from openai import AsyncOpenAI

from agents.base_agent import ScalpingContext, MarketDecision
from agents.claude_agent import _parse_json
from config import settings

logger = logging.getLogger(__name__)


def _get_session() -> str:
    """현재 시각 기준 세션 반환: 'AM' | 'PM'."""
    now = datetime.now().strftime("%H:%M")
    if now <= settings.SCALPING_AM_END:
        return "AM"
    return "PM"


class FilterAgent:
    """시장 상황 필터 Agent (Llama-3.1-8b)."""

    def __init__(self):
        self._client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )

    def _system_prompt(self, session: str) -> str:
        if session == "AM":
            return (
                "당신은 한국 주식 단타 매매 시장 상황 분석 전문가입니다.\n"
                "오전 장(09:30~11:59) 기준으로 거래량 급등 초기 진입이 적합한지 판단합니다.\n"
                "핵심 기준: 거래량 배수 3.0x 이상, 당일 등락률 과열 아님, 코스피 방향성 확인.\n"
                "응답은 반드시 지정된 JSON 형식으로만 작성하세요."
            )
        else:
            return (
                "당신은 한국 주식 단타 매매 시장 상황 분석 전문가입니다.\n"
                "오후 장(12:00~14:50) 기준으로 눌림목 반등 또는 오후 신규 테마 상승 초기 진입이 적합한지 판단합니다.\n"
                "핵심 기준: 거래량 배수 1.5x 이상, 당일 등락률 1~8% 사이(과열 아님), 코스피 방향성 확인.\n"
                "오전에 이미 10% 이상 급등한 종목은 오후 재진입 위험이 높으므로 NO-GO.\n"
                "응답은 반드시 지정된 JSON 형식으로만 작성하세요."
            )

    async def _call(self, prompt: str, session: str) -> str:
        response = await self._client.chat.completions.create(
            model=settings.GROQ_MODEL_C,
            max_tokens=600,
            temperature=0.2,
            messages=[
                {"role": "system", "content": self._system_prompt(session)},
                {"role": "user",   "content": prompt},
            ],
        )
        return response.choices[0].message.content

    def _check_rules(self, ctx: ScalpingContext, session: str) -> tuple[bool, str]:
        """규칙 기반 사전 필터 (LLM 호출 전 빠른 체크)."""
        now = datetime.now()
        time_str = now.strftime("%H:%M")

        # 공통: 거래 시작 전
        if time_str < settings.SCALPING_EXEC_START:
            return False, f"거래 시간 전 ({time_str} < {settings.SCALPING_EXEC_START})"
        # 공통: 거래 종료 후
        if time_str > settings.SCALPING_EXEC_END:
            return False, f"거래 시간 종료 ({time_str} > {settings.SCALPING_EXEC_END})"

        # 공통: 코스피 방향 불명확
        if abs(ctx.kospi_change_rate) <= settings.SCALPING_KOSPI_RANGE * 100:
            return False, f"코스피 방향 불명확 ({ctx.kospi_change_rate:+.2f}%)"

        if session == "AM":
            # 갭 필터
            if ctx.open_price > 0 and ctx.minute_candles:
                prev_close = ctx.minute_candles[0].get("close", ctx.open_price)
                if prev_close > 0:
                    gap = abs(ctx.open_price - prev_close) / prev_close
                    if gap >= settings.SCALPING_AM_GAP_LIMIT:
                        return False, f"갭 과대 ({gap:.1%} ≥ {settings.SCALPING_AM_GAP_LIMIT:.0%})"
            # 상한가 근접
            if ctx.change_rate >= settings.SCALPING_AM_CHANGE_RATE_MAX:
                return False, f"상한가 근접 ({ctx.change_rate:+.2f}%)"
            # 거래량 기준
            if ctx.volume_ratio < settings.SCALPING_AM_VOLUME_SURGE:
                return False, f"오전 거래량 부족 ({ctx.volume_ratio:.1f}x < {settings.SCALPING_AM_VOLUME_SURGE}x)"

        else:  # PM
            # 갭 필터 (완화)
            if ctx.open_price > 0 and ctx.minute_candles:
                prev_close = ctx.minute_candles[0].get("close", ctx.open_price)
                if prev_close > 0:
                    gap = abs(ctx.open_price - prev_close) / prev_close
                    if gap >= settings.SCALPING_PM_GAP_LIMIT:
                        return False, f"갭 과대 ({gap:.1%} ≥ {settings.SCALPING_PM_GAP_LIMIT:.0%})"
            # 등락률 범위 필터 (1~8%)
            if ctx.change_rate < settings.SCALPING_PM_CHANGE_RATE_MIN:
                return False, f"오후 모멘텀 부족 (등락률 {ctx.change_rate:+.2f}% < +{settings.SCALPING_PM_CHANGE_RATE_MIN}%)"
            if ctx.change_rate >= settings.SCALPING_PM_CHANGE_RATE_MAX:
                return False, f"오후 과열 종목 제외 (등락률 {ctx.change_rate:+.2f}% ≥ +{settings.SCALPING_PM_CHANGE_RATE_MAX}%)"
            # 거래량 기준 (완화)
            if ctx.volume_ratio < settings.SCALPING_PM_VOLUME_SURGE:
                return False, f"오후 거래량 부족 ({ctx.volume_ratio:.1f}x < {settings.SCALPING_PM_VOLUME_SURGE}x)"

        return True, "사전 규칙 통과"

    async def analyze(self, ctx: ScalpingContext) -> MarketDecision:
        session = _get_session()

        # 규칙 기반 사전 필터 (빠른 판단)
        rule_pass, rule_reason = self._check_rules(ctx, session)
        if not rule_pass:
            logger.info("[FilterAgent][%s] %s → NO-GO (%s)", session, ctx.stock_code, rule_reason)
            return MarketDecision(go=False, confidence=1.0, reasoning=rule_reason)

        # LLM 최종 판단
        if session == "AM":
            strategy_note = (
                "오전 전략: 거래량 급등 초기 포착. "
                f"거래량 배수 {ctx.volume_ratio:.1f}x "
                f"(기준 {settings.SCALPING_AM_VOLUME_SURGE}x 이상 — 이미 규칙 통과)."
            )
        else:
            strategy_note = (
                "오후 전략: 눌림목 반등 또는 오후 신규 테마 상승 초기 포착. "
                f"거래량 배수 {ctx.volume_ratio:.1f}x "
                f"(기준 {settings.SCALPING_PM_VOLUME_SURGE}x 이상 — 이미 규칙 통과), "
                f"등락률 {ctx.change_rate:+.2f}% "
                f"(기준 +{settings.SCALPING_PM_CHANGE_RATE_MIN}~{settings.SCALPING_PM_CHANGE_RATE_MAX}% — 이미 규칙 통과). "
                "사전 규칙을 이미 통과한 종목이므로, 시장 흐름상 진입이 유망한지 최종 판단하세요."
            )

        prompt = f"""
## 현재 시장 상황
코스피 등락률: {ctx.kospi_change_rate:+.2f}%
현재 시각: {datetime.now().strftime('%H:%M')}  세션: {'오전' if session == 'AM' else '오후'}

## 분석 종목
종목: {ctx.stock_code} {ctx.stock_name}
현재가: {ctx.current_price:,}원  등락률: {ctx.change_rate:+.2f}%
거래량 배수: {ctx.volume_ratio:.1f}x

## 사전 규칙 체크 결과: 통과
{strategy_note}

## 판단 요청
시장 전체 방향성과 종목 수급 측면에서 지금 진입이 적합한지 판단하세요.

다음 JSON 형식으로만 응답하세요:
{{
  "go": true | false,
  "confidence": 0.0~1.0,
  "reasoning": "시장 상황 판단 근거 (1~2문장)"
}}
"""
        raw = await self._call(prompt, session)
        data = _parse_json(raw)

        decision = MarketDecision(
            go         = bool(data.get("go", False)),
            confidence = float(data.get("confidence", 0.5)),
            reasoning  = data.get("reasoning", rule_reason),
        )
        logger.info("[FilterAgent][%s] %s → %s (확신도: %.0f%%) %s",
                    session,
                    ctx.stock_code,
                    "GO" if decision.go else "NO-GO",
                    decision.confidence * 100,
                    decision.reasoning[:60])
        return decision
