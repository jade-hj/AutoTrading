"""
주문 실행 관리자

합의 결과를 받아 KIS API로 실제 주문을 실행한다.
손절/익절 강제 매도를 먼저 처리한 후 합의 결과를 실행한다.
"""
from agents.consensus import ConsensusResult
from agents.base_agent import Action
from trading.portfolio import Portfolio
from kis import rest_client as kis
import logging

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(self, portfolio: Portfolio):
        self.portfolio = portfolio

    def execute(self, consensus: ConsensusResult) -> list[dict]:
        """
        1. 손절/익절 강제 매도 먼저 처리
        2. 합의 결과 실행
        반환: 실행된 주문 목록
        """
        executed = []

        # ── 1. 손절/익절 강제 매도 ───────────────────────────
        forced_sells = self.portfolio.get_forced_sell_stocks()
        for stock_code in forced_sells:
            qty = self.portfolio.calc_sell_quantity(stock_code)
            if qty > 0:
                try:
                    order = kis.place_order(stock_code, "SELL", qty)
                    order["reason"] = "강제매도(손절/익절)"
                    executed.append(order)
                    logger.info(f"강제 매도 실행: {stock_code} {qty}주")
                except Exception as e:
                    logger.error(f"강제 매도 실패: {stock_code} — {e}")

        # ── 2. 합의 결과 실행 ────────────────────────────────
        if not consensus.is_consensus:
            logger.info("합의 실패 — 주문 없음 (HOLD)")
            return executed

        action     = consensus.action
        stock_code = consensus.stock_code

        if action == Action.HOLD or not stock_code:
            logger.info("합의 결과: HOLD — 주문 없음")
            return executed

        if action == Action.BUY:
            executed += self._buy(consensus)
        elif action == Action.SELL:
            executed += self._sell(consensus)

        return executed

    def _buy(self, consensus: ConsensusResult) -> list[dict]:
        stock_code = consensus.stock_code
        try:
            price_info = kis.get_current_price(stock_code)
            current_price = price_info["current_price"]
        except Exception as e:
            logger.error(f"현재가 조회 실패: {stock_code} — {e}")
            return []

        # Agent 제안 비중 평균 (votes에서 추출)
        avg_ratio = 0.15  # 기본값
        qty = self.portfolio.calc_buy_quantity(stock_code, current_price, avg_ratio)

        if qty <= 0:
            logger.warning(f"매수 수량 0 — 자금 부족 또는 이미 최대 비중: {stock_code}")
            return []

        try:
            order = kis.place_order(stock_code, "BUY", qty)
            order["reason"] = f"합의 매수 ({consensus.vote_count}/{consensus.total_agents}표)"
            logger.info(f"매수 주문 실행: {stock_code} {qty}주 @ {current_price:,}원")
            return [order]
        except Exception as e:
            logger.error(f"매수 주문 실패: {stock_code} — {e}")
            return []

    def _sell(self, consensus: ConsensusResult) -> list[dict]:
        stock_code = consensus.stock_code
        qty = self.portfolio.calc_sell_quantity(stock_code)

        if qty <= 0:
            logger.warning(f"매도할 보유 수량 없음: {stock_code}")
            return []

        try:
            order = kis.place_order(stock_code, "SELL", qty)
            order["reason"] = f"합의 매도 ({consensus.vote_count}/{consensus.total_agents}표)"
            logger.info(f"매도 주문 실행: {stock_code} {qty}주")
            return [order]
        except Exception as e:
            logger.error(f"매도 주문 실패: {stock_code} — {e}")
            return []
