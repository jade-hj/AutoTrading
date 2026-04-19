"""
포지션 및 손익 추적

매 실행 주기마다 잔고를 조회하고 포지션 현황을 로깅한다.
"""
from kis import rest_client as kis
from trading.portfolio import Portfolio
import logging

logger = logging.getLogger(__name__)


class PositionTracker:
    def __init__(self):
        self._last_balance: dict = {}

    def refresh(self) -> Portfolio:
        """잔고 조회 후 Portfolio 객체 반환"""
        balance = kis.get_balance()
        self._last_balance = balance
        self._log_positions(balance)
        return Portfolio(
            available_cash = balance["available_cash"],
            total_value    = balance["total_eval"],
            holdings       = balance["holdings"],
        )

    def _log_positions(self, balance: dict) -> None:
        logger.info(
            f"잔고 현황 | 예수금: {balance['available_cash']:,}원 | "
            f"총평가: {balance['total_eval']:,}원"
        )
        for h in balance["holdings"]:
            logger.info(
                f"  [{h['stock_code']}] {h['stock_name']} "
                f"{h['quantity']}주 | 평균단가: {h['avg_price']:,.0f}원 | "
                f"손익률: {h['profit_loss']:+.2f}%"
            )

    @property
    def holdings(self) -> list[dict]:
        return self._last_balance.get("holdings", [])
