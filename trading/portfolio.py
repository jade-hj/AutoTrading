"""
포트폴리오 관리 — 자금 배분 및 주문 수량 계산
"""
from config import settings
import logging

logger = logging.getLogger(__name__)


class Portfolio:
    def __init__(self, available_cash: int, total_value: int, holdings: list[dict]):
        self.available_cash = available_cash
        self.total_value    = total_value
        self.holdings       = holdings  # rest_client.get_balance()["holdings"]

    def calc_buy_quantity(
        self,
        stock_code: str,
        current_price: int,
        quantity_ratio: float,
    ) -> int:
        """
        매수 수량 계산.
        quantity_ratio: Agent가 제안한 포트폴리오 대비 비중 (0.0 ~ 1.0)
        MAX_POSITION_RATIO 초과 불가.
        """
        ratio = min(quantity_ratio, settings.MAX_POSITION_RATIO)

        # 이미 보유 중인 경우 기존 비중 차감
        existing_value = self._get_holding_value(stock_code)
        investable_value = self.total_value * ratio - existing_value
        investable_value = min(investable_value, self.available_cash)

        if investable_value <= 0 or current_price <= 0:
            return 0

        quantity = int(investable_value // current_price)
        logger.info(
            f"매수 수량 계산: {stock_code} | 비중: {ratio:.0%} | "
            f"투자금: {investable_value:,.0f}원 | 수량: {quantity}주"
        )
        return quantity

    def calc_sell_quantity(self, stock_code: str) -> int:
        """보유 수량 전량 반환"""
        for h in self.holdings:
            if h["stock_code"] == stock_code:
                return h["quantity"]
        return 0

    def should_stop_loss(self, stock_code: str) -> bool:
        """손절 기준 도달 여부"""
        for h in self.holdings:
            if h["stock_code"] == stock_code:
                return h["profit_loss"] <= -settings.STOP_LOSS_RATIO * 100
        return False

    def should_take_profit(self, stock_code: str) -> bool:
        """익절 기준 도달 여부"""
        for h in self.holdings:
            if h["stock_code"] == stock_code:
                return h["profit_loss"] >= settings.TAKE_PROFIT_RATIO * 100
        return False

    def get_forced_sell_stocks(self) -> list[str]:
        """손절/익절 기준 도달 종목 목록"""
        forced = []
        for h in self.holdings:
            code = h["stock_code"]
            if self.should_stop_loss(code):
                logger.warning(f"손절 기준 도달: {code} ({h['profit_loss']:+.2f}%)")
                forced.append(code)
            elif self.should_take_profit(code):
                logger.info(f"익절 기준 도달: {code} ({h['profit_loss']:+.2f}%)")
                forced.append(code)
        return forced

    def _get_holding_value(self, stock_code: str) -> int:
        for h in self.holdings:
            if h["stock_code"] == stock_code:
                return int(h["quantity"] * h["current_price"])
        return 0
