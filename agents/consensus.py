"""
다수결 합의 엔진

3개 Agent의 최종 투표를 집계해 실행할 행동을 결정한다.

규칙:
- 같은 action + 같은 stock_code로 2표 이상 → 실행
- 합의 실패(모두 다른 종목/액션) → HOLD
- SELL이 2표 이상이면 stock_code는 현재 보유 종목에서 매칭
"""
from collections import Counter
from dataclasses import dataclass
from agents.base_agent import FinalVote, Action
import logging

logger = logging.getLogger(__name__)


@dataclass
class ConsensusResult:
    action:       Action
    stock_code:   str
    stock_name:   str
    vote_count:   int           # 찬성 표 수
    total_agents: int           # 전체 Agent 수
    reasoning:    str           # 다수 의견 근거 합본
    all_votes:    list[FinalVote]
    is_consensus: bool          # 합의 성공 여부

    @property
    def vote_summary(self) -> str:
        lines = [f"합의 결과: {self.action} {self.stock_code} {self.stock_name} "
                 f"({self.vote_count}/{self.total_agents}표)"]
        for v in self.all_votes:
            lines.append(f"  - {v.agent_name}: {v.action} {v.stock_code}")
        return "\n".join(lines)


def decide(votes: list[FinalVote]) -> ConsensusResult:
    """
    다수결 집계 후 ConsensusResult 반환.
    """
    total = len(votes)

    # (action, stock_code) 조합으로 집계
    counter: Counter = Counter(
        (v.action, v.stock_code) for v in votes
    )
    most_common, count = counter.most_common(1)[0]
    best_action, best_stock = most_common

    # 과반(2/3) 이상이어야 합의로 인정
    if count >= 2:
        # 종목명, 근거는 해당 투표에서 추출
        matching = [v for v in votes if v.action == best_action and v.stock_code == best_stock]
        stock_name = matching[0].stock_name if matching else ""
        reasoning  = " | ".join(v.reasoning for v in matching)

        result = ConsensusResult(
            action       = best_action,
            stock_code   = best_stock,
            stock_name   = stock_name,
            vote_count   = count,
            total_agents = total,
            reasoning    = reasoning,
            all_votes    = votes,
            is_consensus = True,
        )
    else:
        # 합의 실패 → HOLD
        reasoning = "3개 Agent가 서로 다른 종목/액션으로 합의 실패 → HOLD"
        result = ConsensusResult(
            action       = Action.HOLD,
            stock_code   = "",
            stock_name   = "",
            vote_count   = 0,
            total_agents = total,
            reasoning    = reasoning,
            all_votes    = votes,
            is_consensus = False,
        )

    logger.info(f"\n{result.vote_summary}")
    return result
