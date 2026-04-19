"""
로깅 설정

파일(logs/trading_YYYYMMDD.log)과 콘솔에 동시 출력.
거래 전용 trade_logger는 별도 파일(logs/trades_YYYYMMDD.log)에 기록.
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


def _setup_root_logger() -> None:
    root = logging.getLogger()
    if root.handlers:
        return
    root.setLevel(logging.INFO)

    # 콘솔 (Windows cp949 환경에서 한글 깨짐 방지)
    sh = logging.StreamHandler(sys.stdout)
    sh.stream.reconfigure(encoding="utf-8", errors="replace") if hasattr(sh.stream, "reconfigure") else None
    sh.setFormatter(logging.Formatter(_FMT, _DATE))
    root.addHandler(sh)

    # 파일
    fh = logging.FileHandler(_LOG_DIR / f"trading_{_TODAY}.log", encoding="utf-8")
    fh.setFormatter(logging.Formatter(_FMT, _DATE))
    root.addHandler(fh)


def get_logger(name: str) -> logging.Logger:
    _setup_root_logger()
    return logging.getLogger(name)


def get_trade_logger() -> logging.Logger:
    """거래 전용 로거 (trades_YYYYMMDD.log)"""
    _setup_root_logger()
    name   = "trade"
    logger = logging.getLogger(name)
    if not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        fh = logging.FileHandler(_LOG_DIR / f"trades_{_TODAY}.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter(_FMT, _DATE))
        logger.addHandler(fh)
        logger.propagate = True
    return logger
