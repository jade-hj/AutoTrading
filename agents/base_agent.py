"""
AI Agent 공통 인터페이스 및 데이터 구조
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Action(str, Enum):
    BUY  = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class AgentProposal:
    """Agent가 Round 1에서 제출하는 제안"""
    agent_name:     str
    action:         Action
    stock_code:     str          # 매수/매도 종목 코드 (HOLD이면 "")
    stock_name:     str          # 종목명
    quantity_ratio: float        # 포트폴리오 대비 비중 (0.0 ~ 1.0)
    reasoning:      str          # 판단 근거
    confidence:     float = 0.5  # 확신도 (0.0 ~ 1.0)


@dataclass
class AgentRebuttal:
    """Agent가 Round 2에서 제출하는 반론/동의"""
    agent_name:    str
    agrees_with:   list[str]     # 동의하는 Agent 이름 목록
    disagrees_with: list[str]    # 반론하는 Agent 이름 목록
    revised_action: Optional[Action] = None   # 입장 변경 시
    revised_stock:  Optional[str]    = None
    comment:        str = ""


@dataclass
class FinalVote:
    """최종 투표"""
    agent_name:  str
    action:      Action
    stock_code:  str
    stock_name:  str
    reasoning:   str


@dataclass
class MarketContext:
    """Agent에게 전달되는 시장 컨텍스트"""
    candidates:        list[dict]    # format_candidates_for_agent 결과 원본
    candidates_text:   str           # 프롬프트용 텍스트
    current_holdings:  list[dict]    # 현재 보유 종목
    available_cash:    int           # 사용 가능 현금 (원)
    total_portfolio:   int           # 총 포트폴리오 가치 (원)


class BaseAgent(ABC):
    """모든 AI Agent의 기본 클래스"""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def propose(self, context: MarketContext) -> AgentProposal:
        """Round 1: 독립적 분석 후 제안"""
        ...

    @abstractmethod
    async def debate(
        self,
        context: MarketContext,
        proposals: list[AgentProposal],   # 모든 Agent의 Round 1 제안
        my_proposal: AgentProposal,
    ) -> AgentRebuttal:
        """Round 2: 다른 Agent 제안에 대한 반론/동의"""
        ...

    @abstractmethod
    async def vote(
        self,
        context: MarketContext,
        proposals: list[AgentProposal],
        rebuttals: list[AgentRebuttal],
    ) -> FinalVote:
        """Round 3: 최종 투표"""
        ...

    # ── 프롬프트 공통 시스템 메시지 ──────────────────────────────
    def _system_prompt(self) -> str:
        return (
            "당신은 한국 주식 시장(KRX) 전문 투자 분석가입니다.\n"
            "제시된 종목 데이터와 기술적 지표를 분석하여 매수(BUY), 매도(SELL), "
            "보류(HOLD) 중 하나를 결정합니다.\n"
            "응답은 반드시 지정된 JSON 형식으로만 작성하세요."
        )

    def _portfolio_context(self, context: MarketContext) -> str:
        lines = [
            f"사용 가능 현금: {context.available_cash:,}원",
            f"총 포트폴리오 가치: {context.total_portfolio:,}원",
        ]
        if context.current_holdings:
            lines.append("현재 보유 종목:")
            for h in context.current_holdings:
                lines.append(
                    f"  - [{h['stock_code']}] {h['stock_name']} "
                    f"{h['quantity']}주 (평균단가: {h['avg_price']:,.0f}원, "
                    f"손익률: {h['profit_loss']:+.2f}%)"
                )
        else:
            lines.append("현재 보유 종목 없음")
        return "\n".join(lines)
