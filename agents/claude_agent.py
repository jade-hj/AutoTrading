"""
Agent A — Groq / Llama-3.3-70b (기술적 분석 전문)

Groq API는 OpenAI-compatible이므로 AsyncOpenAI + base_url 변경으로 사용.
"""
import json
import logging

from openai import AsyncOpenAI

from agents.base_agent import (
    Action, AgentProposal, AgentRebuttal, BaseAgent, FinalVote, MarketContext,
)
from config import settings

logger = logging.getLogger(__name__)


class ClaudeAgent(BaseAgent):
    """기술적 분석 전문 Agent (Groq Llama-3.3-70b)."""

    def __init__(self):
        super().__init__("Llama(기술분석)")
        self._client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )

    def _system_prompt(self) -> str:
        return (
            "당신은 한국 주식 시장(KRX) 전문 기술적 분석가입니다.\n"
            "이동평균(MA), RSI, MACD, 볼린저밴드 등 기술적 지표를 중심으로 분석하여 "
            "매수(BUY), 매도(SELL), 보류(HOLD)를 결정합니다.\n"
            "응답은 반드시 지정된 JSON 형식으로만 작성하세요."
        )

    async def _call(self, user_prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=settings.GROQ_MODEL_A,
            max_tokens=settings.MAX_TOKENS_PER_AGENT,
            temperature=0.4,
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {"role": "user",   "content": user_prompt},
            ],
        )
        return response.choices[0].message.content

    # ── Round 1: 제안 ────────────────────────────────────────
    async def propose(self, context: MarketContext) -> AgentProposal:
        prompt = f"""
{context.candidates_text}

## 포트폴리오 현황
{self._portfolio_context(context)}

## 당신의 역할
기술적 분석(이동평균, RSI, MACD, 볼린저밴드) 전문가로서 위 종목들을 분석하세요.
매수 기회가 있는 종목, 또는 보유 중이라면 매도 시점인지 판단하세요.

다음 JSON 형식으로만 응답하세요:
{{
  "action": "BUY" | "SELL" | "HOLD",
  "stock_code": "종목코드 (HOLD이면 빈 문자열)",
  "stock_name": "종목명 (HOLD이면 빈 문자열)",
  "quantity_ratio": 0.0~1.0 (포트폴리오 대비 투자 비중, HOLD이면 0),
  "confidence": 0.0~1.0,
  "reasoning": "판단 근거 (기술적 지표 중심으로 구체적으로)"
}}
"""
        raw = await self._call(prompt)
        data = _parse_json(raw)
        proposal = AgentProposal(
            agent_name     = self.name,
            action         = Action(data.get("action", "HOLD")),
            stock_code     = data.get("stock_code", ""),
            stock_name     = data.get("stock_name", ""),
            quantity_ratio = float(data.get("quantity_ratio", 0.0)),
            confidence     = float(data.get("confidence", 0.5)),
            reasoning      = data.get("reasoning", ""),
        )
        logger.info("[%s] 제안: %s %s | %s...", self.name, proposal.action, proposal.stock_code, proposal.reasoning[:80])
        return proposal

    # ── Round 2: 토론 ────────────────────────────────────────
    async def debate(
        self,
        context: MarketContext,
        proposals: list[AgentProposal],
        my_proposal: AgentProposal,
    ) -> AgentRebuttal:
        others_text = _format_proposals(proposals, exclude=self.name)
        prompt = f"""
## 다른 Agent들의 제안
{others_text}

## 당신의 기존 제안
Action: {my_proposal.action}, 종목: {my_proposal.stock_code} {my_proposal.stock_name}
근거: {my_proposal.reasoning}

## 토론
각 Agent의 제안을 검토하고 동의 또는 반론하세요. 필요하다면 입장을 변경할 수 있습니다.

다음 JSON 형식으로만 응답하세요:
{{
  "agrees_with": ["동의하는 Agent 이름 목록"],
  "disagrees_with": ["반론하는 Agent 이름 목록"],
  "revised_action": "BUY" | "SELL" | "HOLD" | null (변경 없으면 null),
  "revised_stock": "종목코드" | null,
  "comment": "토론 내용"
}}
"""
        raw = await self._call(prompt)
        data = _parse_json(raw)
        revised_action = data.get("revised_action")
        return AgentRebuttal(
            agent_name     = self.name,
            agrees_with    = data.get("agrees_with", []),
            disagrees_with = data.get("disagrees_with", []),
            revised_action = Action(revised_action) if revised_action else None,
            revised_stock  = data.get("revised_stock"),
            comment        = data.get("comment", ""),
        )

    # ── Round 3: 최종 투표 ───────────────────────────────────
    async def vote(
        self,
        context: MarketContext,
        proposals: list[AgentProposal],
        rebuttals: list[AgentRebuttal],
    ) -> FinalVote:
        prompt = f"""
## 전체 제안 요약
{_format_proposals(proposals)}

## 토론 내용
{_format_rebuttals(rebuttals)}

## 최종 투표
모든 토론을 검토한 후 최종 결정을 내리세요.

다음 JSON 형식으로만 응답하세요:
{{
  "action": "BUY" | "SELL" | "HOLD",
  "stock_code": "종목코드 (HOLD이면 빈 문자열)",
  "stock_name": "종목명 (HOLD이면 빈 문자열)",
  "reasoning": "최종 판단 근거"
}}
"""
        raw = await self._call(prompt)
        data = _parse_json(raw)
        vote = FinalVote(
            agent_name = self.name,
            action     = Action(data.get("action", "HOLD")),
            stock_code = data.get("stock_code", ""),
            stock_name = data.get("stock_name", ""),
            reasoning  = data.get("reasoning", ""),
        )
        logger.info("[%s] 최종 투표: %s %s", self.name, vote.action, vote.stock_code)
        return vote


# ── 헬퍼 (다른 agent들이 import해서 사용) ────────────────────────

def _parse_json(text: str) -> dict:
    """LLM 응답에서 JSON 추출.

    - <think>...</think> CoT 블록 제거 (Qwen3 등 reasoning 모델 대응)
    - ```json ... ``` 코드 블록 처리
    - 중괄호 범위 추출
    """
    import re
    text = text.strip()
    # <think>...</think> 블록 제거
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    # 코드 블록 처리
    if "```" in text:
        start = text.find("{")
        end   = text.rfind("}") + 1
        if start != -1 and end > start:
            text = text[start:end]
    # JSON 객체 범위 추출
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        logger.warning("JSON 파싱 실패, 기본값 반환: %s", text[:200])
        return {}


def _format_proposals(proposals: list[AgentProposal], exclude: str = "") -> str:
    lines = []
    for p in proposals:
        if p.agent_name == exclude:
            continue
        lines.append(
            f"**{p.agent_name}**: {p.action} | {p.stock_code} {p.stock_name} "
            f"(확신도: {p.confidence:.0%})\n  근거: {p.reasoning}"
        )
    return "\n\n".join(lines)


def _format_rebuttals(rebuttals: list[AgentRebuttal]) -> str:
    lines = []
    for r in rebuttals:
        lines.append(
            f"**{r.agent_name}**: {r.comment}"
            + (f" → 입장 변경: {r.revised_action} {r.revised_stock}" if r.revised_action else "")
        )
    return "\n".join(lines)
