"""
로깅 설정

파일(logs/trading_YYYYMMDD.log)과 콘솔에 동시 출력.
거래 전용 trade 로거는 logs/trades_YYYYMMDD.log 에 별도 기록.

trade_log.log_buy()  / trade_log.log_sell() 로 매매 기록 남김.
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
_LOG_DIR.mkdir(exist_ok=True)

_TODAY = datetime.now().strftime("%Y%m%d")
_FMT   = "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
_DATE  = "%H:%M:%S"
_SEP   = "=" * 72


def setup_logger() -> None:
    """루트 로거 초기화 (main.py 진입점에서 1회 호출)."""
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)

    # 콘솔 — Windows cmd 한글 깨짐 방지
    sh = logging.StreamHandler(sys.stdout)
    if hasattr(sh.stream, "reconfigure"):
        sh.stream.reconfigure(encoding="utf-8", errors="replace")
    sh.setFormatter(logging.Formatter(_FMT, _DATE))
    root.addHandler(sh)

    # 시스템 로그 파일
    fh = logging.FileHandler(_LOG_DIR / f"trading_{_TODAY}.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter(_FMT, _DATE))
    root.addHandler(fh)


def _get_trade_logger() -> logging.Logger:
    """거래 전용 로거 (trades_YYYYMMDD.log + 콘솔 동시 출력)."""
    name   = "trade"
    logger = logging.getLogger(name)
    if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        fh = logging.FileHandler(_LOG_DIR / f"trades_{_TODAY}.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(message)s"))  # 거래 로그는 메시지만 기록
        logger.addHandler(fh)
        logger.propagate = True  # 콘솔(root handler)로도 전달
    return logger


class TradeLogger:
    """매수 / 매도 이벤트를 구조화된 형식으로 파일 + 콘솔에 기록한다."""

    def __init__(self):
        self._logger = _get_trade_logger()

    # ── 시장 현황 로그 ───────────────────────────────────────────
    def log_market_status(
        self,
        kospi: dict,
        balance: dict,
        candidates: list[dict],
        mode: str = "모의투자",
    ) -> None:
        """시스템 시작 시 시장 현황을 콘솔 + 파일에 기록한다."""
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 코스피 라인
        idx   = kospi.get("index", 0.0)
        rate  = kospi.get("change_rate", 0.0)
        chg   = kospi.get("change", 0.0)
        vol   = kospi.get("volume", 0)
        sign  = "▲" if rate >= 0 else "▼"
        kospi_line = (
            f"  KOSPI   : {idx:,.2f}  {sign}{abs(chg):.2f} ({rate:+.2f}%)  "
            f"거래량: {vol:,}"
            if idx else "  KOSPI   : 조회 실패"
        )

        # 계좌 라인
        cash  = balance.get("available_cash", 0)
        total = balance.get("total_eval",     0)
        holds = balance.get("holdings",       [])

        holding_lines = []
        if holds:
            for h in holds:
                pnl_sign = "+" if h["profit_loss"] >= 0 else ""
                holding_lines.append(
                    f"    [{h['stock_code']}] {h['stock_name']}  "
                    f"{h['quantity']:,}주  평균단가: {h['avg_price']:,.0f}원  "
                    f"손익: {pnl_sign}{h['profit_loss']:.2f}%"
                )
        else:
            holding_lines.append("    보유 종목 없음")

        # 거래량 상위 후보 종목 라인
        cand_lines = []
        for i, c in enumerate(candidates[:10], 1):
            rr = c.get("change_rate", 0.0)
            cs = "+" if rr >= 0 else ""
            cand_lines.append(
                f"    {i:2d}. [{c['stock_code']}] {c['stock_name']:<12}  "
                f"{c['current_price']:>8,}원  ({cs}{rr:.2f}%)  "
                f"거래량: {c['volume']:>12,}"
            )

        lines = [
            _SEP,
            f"[시장 현황] {ts}  ({mode})",
            "",
            "  ── 지수 ──────────────────────────────────────────────",
            kospi_line,
            "",
            "  ── 계좌 ──────────────────────────────────────────────",
            f"  예수금  : {cash:,}원",
            f"  총평가  : {total:,}원",
            f"  보유종목: {len(holds)}개",
            *holding_lines,
            "",
            "  ── 거래량 상위 후보 종목 ─────────────────────────────",
            *cand_lines,
            _SEP,
        ]
        self._logger.info("\n" + "\n".join(lines))

    # ── 매수 로그 ─────────────────────────────────────────────
    def log_buy(
        self,
        stock_code:    str,
        stock_name:    str,
        buy_price:     int,
        quantity:      int,
        signal_action: str,
        signal_conf:   float,
        signal_reason: str,
        risk_reason:   str,
        stop_loss:     int,
        tp1:           int,
        tp2:           int,
        market_reason: str,
        order_no:      str = "",
    ) -> None:
        invest = buy_price * quantity
        ts     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            _SEP,
            f"[매수] {ts}  주문번호: {order_no}",
            f"  종목    : {stock_code} {stock_name}",
            f"  매수가  : {buy_price:,}원  |  수량: {quantity:,}주  |  투자금: {invest:,}원",
            f"  손절가  : {stop_loss:,}원  |  1차익절: {tp1:,}원  |  2차익절: {tp2:,}원",
            "",
            f"  [신호 Agent] {signal_action}  확신도: {signal_conf:.0%}",
            f"    {signal_reason}",
            f"  [리스크 Agent] OK",
            f"    {risk_reason}",
            f"  [시장 필터] GO",
            f"    {market_reason}",
            _SEP,
        ]
        self._logger.info("\n" + "\n".join(lines))

    # ── 매도 로그 ─────────────────────────────────────────────
    def log_sell(
        self,
        stock_code:  str,
        stock_name:  str,
        sell_price:  int,
        quantity:    int,
        entry_price: int,
        reason:      str,
        order_no:    str = "",
    ) -> None:
        diff        = sell_price - entry_price               # 주당 차액 (원)
        total_pnl   = diff * quantity                        # 총 실현 손익 (원)
        pnl_rate    = diff / entry_price * 100 if entry_price else 0
        sign        = "+" if total_pnl >= 0 else ""
        ts          = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = [
            _SEP,
            f"[매도] {ts}  주문번호: {order_no}  사유: {reason}",
            f"  종목    : {stock_code} {stock_name}",
            f"  매수가  : {entry_price:,}원  →  매도가: {sell_price:,}원  |  수량: {quantity:,}주",
            f"  주당차액: {sign}{diff:,}원  |  실현손익: {sign}{total_pnl:,}원  ({sign}{pnl_rate:.2f}%)",
            _SEP,
        ]
        self._logger.info("\n" + "\n".join(lines))


# 모듈 레벨 싱글턴 — 어디서든 import 해서 바로 사용
trade_log = TradeLogger()
