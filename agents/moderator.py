"""
토론 진행 오케스트레이터 (Moderator)

3개 Agent를 대상으로 Round 1 → Round 2 → 최종 투표 순서로 토론을 진행한다.
각 라운드는 병렬 실행해 속도를 최적화한다.
"""
import asyncio
from dataclasses import dataclass
from agents.base_agent import (
    BaseAgent, AgentProposal, AgentRebuttal, FinalVote, MarketContext,
)
import logging

logger = logging.getLogger(__name__)


@dataclass
class DebateResult:
    proposals:  list[AgentProposal]
    rebuttals:  list[AgentRebuttal]
    final_votes: list[FinalVote]


class Moderator:
    def __init__(self, agents: list[BaseAgent]):
        assert len(agents) == 3, "합의체는 반드시 3개 Agent로 구성해야 합니다."
        self.agents = agents

    async def run_debate(self, context: MarketContext) -> DebateResult:
        """전체 토론 진행"""
        logger.info("=" * 60)
        logger.info("토론 시작")

        # ── Round 1: 병렬 개별 제안 ──────────────────────────
        logger.info("[Round 1] 개별 분석 & 제안")
        proposals: list[AgentProposal] = await asyncio.gather(
            *[agent.propose(context) for agent in self.agents]
        )
        self._log_round("Round 1 제안", proposals)

        # ── Round 2: 병렬 반론 ───────────────────────────────
        logger.info("[Round 2] 상호 반론 & 토론")
        rebuttals: list[AgentRebuttal] = await asyncio.gather(
            *[
                agent.debate(context, proposals, proposals[i])
                for i, agent in enumerate(self.agents)
            ]
        )
        self._log_rebuttals(rebuttals)

        # ── 최종 투표: 병렬 ──────────────────────────────────
        logger.info("[최종 투표]")
        final_votes: list[FinalVote] = await asyncio.gather(
            *[agent.vote(context, proposals, rebuttals) for agent in self.agents]
        )
        self._log_votes(final_votes)

        logger.info("토론 종료")
        logger.info("=" * 60)
        return DebateResult(
            proposals   = list(proposals),
            rebuttals   = list(rebuttals),
            final_votes = list(final_votes),
        )

    # ── 로깅 헬퍼 ────────────────────────────────────────────
    def _log_round(self, title: str, proposals) -> None:
        logger.info(f"\n--- {title} ---")
        for p in proposals:
            logger.info(
                f"  {p.agent_name}: {p.action} {p.stock_code} {p.stock_name} "
                f"(확신도: {p.confidence:.0%})"
            )

    def _log_rebuttals(self, rebuttals) -> None:
        logger.info("\n--- 토론 내용 ---")
        for r in rebuttals:
            changed = f" → {r.revised_action} {r.revised_stock}" if r.revised_action else ""
            logger.info(f"  {r.agent_name}: {r.comment[:100]}{changed}")

    def _log_votes(self, votes) -> None:
        logger.info("\n--- 최종 투표 ---")
        for v in votes:
            logger.info(f"  {v.agent_name}: {v.action} {v.stock_code} {v.stock_name}")
