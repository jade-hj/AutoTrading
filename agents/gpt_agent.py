"""
Agent B — Groq / Mixtral-8x7b (리스크 관리 전문)

Groq API는 OpenAI-compatible이므로 AsyncOpenAI + base_url 변경으로 사용.
"""
import json
import logging

from openai import AsyncOpenAI

from agents.base_agent import (
    Action, AgentProposal, AgentRebuttal, BaseAgent, FinalVote, MarketContext,
)
from agents.claude_agent import _format_proposals, _format_rebuttals, _parse_json
from config import settings

logger = logging.getLogger(__name__)


class GPTAgent(BaseAgent):
    """리스크 관리 전문 Agent (Groq Mixtral-8x7b)."""

    def __init__(self):
        super().__init__("Mixtral(리스크관리)")
        self._client = AsyncOpenAI(
            api_key=settings.GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )

    async def _call(self, user_prompt: str) -> str:
        response = await self._client.chat.completions.create(
            model=settings.GROQ_MODEL_B,
            max_tokens=settings.MAX_TOKENS_PER_AGENT,
            temperature=0.4,
            messages=[
                {"role": "system", "content": self._system_prompt()},
                {"role": "user",   "content": user_prompt},
            ],
        )
        return response.choices[0].message.content

    def _system_prompt(self) -> str:
        return (
            "당신은 한국 주식 시장(KRX) 전문 리스크 관리 분석가입니다.\n"
            "손실 방어와 포지션 크기 조절을 최우선으로 고려하여 "
            "매수(BUY), 매도(SELL), 보류(HOLD)를 결정합니다.\n"
            "변동성, 손절/익절 기준, 포트폴리오 집중도를 반드시 검토하세요.\n"
            "응답은 반드시 지정된 JSON 형식으로만 작성하세요."
        )

    async def propose(self, context: MarketContext) -> AgentProposal:
        prompt = f"""
{context.candidates_text}

## 포트폴리오 현황
{self._portfolio_context(context)}
손절 기준: {settings.STOP_LOSS_RATIO:.0%} | 익절 기준: {settings.TAKE_PROFIT_RATIO:.0%}
종목당 최대 비중: {settings.MAX_POSITION_RATIO:.0%}

## 당신의 역할
리스크 관리 전문가로서 손실 가능성과 포트폴리오 안정성을 최우선으로 분석하세요.
현재 보유 종목 중 손절/익절 기준에 도달한 종목이 있는지 먼저 확인하세요.

다음 JSON 형식으로만 응답하세요:
{{
  "action": "BUY" | "SELL" | "HOLD",
  "stock_code": "종목코드 (HOLD이면 빈 문자열)",
  "stock_name": "종목명 (HOLD이면 빈 문자열)",
  "quantity_ratio": 0.0~1.0,
  "confidence": 0.0~1.0,
  "reasoning": "리스크 관점의 판단 근거"
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
        logger.info(f"[{self.name}] 제안: {proposal.action} {proposal.stock_code} | {proposal.reasoning[:80]}...")
        return proposal

    async def debate(
        self, context: MarketContext,
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

## 토론 (리스크 관리 관점에서 검토)
각 Agent의 제안이 리스크 측면에서 적절한지 평가하세요.

다음 JSON 형식으로만 응답하세요:
{{
  "agrees_with": ["동의하는 Agent 이름 목록"],
  "disagrees_with": ["반론하는 Agent 이름 목록"],
  "revised_action": "BUY" | "SELL" | "HOLD" | null,
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

    async def vote(
        self, context: MarketContext,
        proposals: list[AgentProposal],
        rebuttals: list[AgentRebuttal],
    ) -> FinalVote:
        prompt = f"""
## 전체 제안 요약
{_format_proposals(proposals)}

## 토론 내용
{_format_rebuttals(rebuttals)}

## 최종 투표 (리스크 관리 관점)
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
        logger.info(f"[{self.name}] 최종 투표: {vote.action} {vote.stock_code}")
        return vote
