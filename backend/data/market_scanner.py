"""
종목 스캐너

KIS API로 거래량 상위 종목을 수집하고 기술적 지표를 포함한 후보 목록을 반환한다.

참고:
  - FHPST01710000 (거래량 순위): KOSPI(J) / KOSDAQ(Q) 각각 호출
  - OHLCV 연속 호출 시 초당 거래 제한(EGW00201) 방지를 위해 딜레이 적용
"""

import logging
import time

from config import settings
from data.indicators import get_all_indicators
from kis import rest_client as kis

logger = logging.getLogger(__name__)

# FHPST01710000 기준 마켓 코드
_MARKET_CODE = {"KOSPI": "J", "KOSDAQ": "Q"}

# OHLCV 호출 간격 (초당 20건 제한 기준)
_OHLCV_CALL_INTERVAL = 0.5


def scan_candidates() -> list[dict]:
    """KOSPI / KOSDAQ 거래량 상위 종목을 스캔해 지표 포함 후보 목록을 반환한다."""
    raw_candidates = []

    for market_name in settings.SCAN_MARKETS:
        market_code = _MARKET_CODE.get(market_name, "J")
        try:
            stocks = kis.get_market_rank(market=market_code, top_n=50)
            for s in stocks:
                s["market"] = market_name
            raw_candidates.extend(stocks)
            logger.info("%s 스캔: %d개", market_name, len(stocks))
        except Exception as e:
            logger.error("%s 종목 스캔 실패: %s", market_name, e)

    # 최소 주가 / 최소 거래량 필터
    filtered = [
        s for s in raw_candidates
        if s["current_price"] >= settings.SCAN_MIN_PRICE
        and s["volume"] >= settings.SCAN_MIN_VOLUME
    ]

    # 절대 거래량 기준 내림차순 정렬 후 상위 N개 * 2 (volume_ratio 계산 후 재정렬)
    filtered.sort(key=lambda x: x["volume"], reverse=True)
    top_candidates = filtered[: settings.SCAN_TOP_N * 2]

    # 일봉 데이터로 volume_ratio(오늘 거래량 / 20일 평균) 및 기술적 지표 계산
    result = []
    for stock in top_candidates:
        code = stock["stock_code"]
        try:
            time.sleep(_OHLCV_CALL_INTERVAL)
            ohlcv = kis.get_ohlcv(code, period="D", count=25)
            indicators = get_all_indicators(ohlcv) if ohlcv else {}

            # volume_ratio: 오늘 누적 거래량 / 직전 20 거래일 평균 거래량
            # ohlcv[0] = 오늘(장중 부분 데이터), ohlcv[1:21] = 직전 20일
            prior_vols = [r["volume"] for r in (ohlcv[1:21] if len(ohlcv) > 1 else ohlcv) if r["volume"] > 0]
            avg_vol = sum(prior_vols) / len(prior_vols) if prior_vols else 1
            volume_ratio = stock["volume"] / avg_vol if avg_vol > 0 else 1.0

            result.append({**stock, "indicators": indicators, "volume_ratio": round(volume_ratio, 2)})
        except Exception as e:
            logger.warning("%s 지표 계산 실패 (스킵): %s", code, e)
            result.append({**stock, "indicators": {}, "volume_ratio": 1.0})

    # volume_ratio 기준 내림차순 정렬 후 상위 N개
    result.sort(key=lambda x: x["volume_ratio"], reverse=True)
    result = result[: settings.SCAN_TOP_N]

    logger.info("종목 스캔 완료: %d개 후보", len(result))
    return result


def format_candidates_for_agent(candidates: list[dict]) -> str:
    """Agent 프롬프트에 삽입할 후보 종목 텍스트를 생성한다."""
    lines = ["## 후보 종목 목록\n"]
    for i, c in enumerate(candidates, 1):
        ind  = c.get("indicators", {})
        rsi  = ind.get("rsi", "N/A")
        macd = ind.get("macd", {})
        ma   = ind.get("ma", {})

        lines.append(
            f"{i}. [{c['stock_code']}] {c.get('stock_name', '')} ({c.get('market', '')})\n"
            f"   현재가: {c['current_price']:,}원 | 등락률: {c['change_rate']:+.2f}% | 거래량: {c['volume']:,}\n"
            f"   RSI: {rsi} | MACD: {macd.get('macd', 'N/A')} (히스토: {macd.get('histogram', 'N/A')})"
            f"{' [골든크로스]' if macd.get('crossover') else ''}\n"
            f"   MA5: {ma.get('ma5', 'N/A')} / MA20: {ma.get('ma20', 'N/A')} / MA60: {ma.get('ma60', 'N/A')}"
            f"{' [정배열]' if ma.get('uptrend') else ''}\n"
        )
    return "\n".join(lines)
