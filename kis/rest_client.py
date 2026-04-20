"""
KIS Open API - REST 클라이언트

참고: https://apiportal.koreainvestment.com/apiservice
"""

import logging
import time
import urllib3
from datetime import datetime, timedelta

import requests

from config import settings
from kis.auth import get_auth

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

# EGW00201: 초당 거래건수 초과 시 재시도 설정
_RATE_LIMIT_CODE = "EGW00201"
_RETRY_COUNT = 3
_RETRY_DELAY = 1.0  # 초


# ------------------------------------------------------------------
# 내부 헬퍼
# ------------------------------------------------------------------

def _get(path: str, tr_id: str, params: dict) -> dict:
    """GET 요청 공통 처리 (rate limit 시 자동 재시도)."""
    auth = get_auth()
    url = f"{settings.KIS_BASE_URL}/{path}"
    for attempt in range(_RETRY_COUNT):
        resp = requests.get(
            url,
            headers=auth.get_headers(tr_id),
            params=params,
            timeout=10,
            verify=False,
        )
        if _is_rate_limited(resp):
            logger.warning("[%s] 초당 거래 제한, %.1f초 후 재시도 (%d/%d)", tr_id, _RETRY_DELAY, attempt + 1, _RETRY_COUNT)
            time.sleep(_RETRY_DELAY)
            continue
        _raise_for_error(resp, tr_id)
        return resp.json()
    raise RuntimeError(f"[{tr_id}] 재시도 초과 ({_RETRY_COUNT}회)")


def _post(path: str, tr_id: str, body: dict) -> dict:
    """POST 요청 공통 처리 (hashkey 포함, rate limit 시 자동 재시도)."""
    auth = get_auth()
    url = f"{settings.KIS_BASE_URL}/{path}"
    for attempt in range(_RETRY_COUNT):
        resp = requests.post(
            url,
            headers=auth.get_headers_with_hashkey(tr_id, body),
            json=body,
            timeout=10,
            verify=False,
        )
        if _is_rate_limited(resp):
            logger.warning("[%s] 초당 거래 제한, %.1f초 후 재시도 (%d/%d)", tr_id, _RETRY_DELAY, attempt + 1, _RETRY_COUNT)
            time.sleep(_RETRY_DELAY)
            continue
        _raise_for_error(resp, tr_id)
        return resp.json()
    raise RuntimeError(f"[{tr_id}] 재시도 초과 ({_RETRY_COUNT}회)")


def _is_rate_limited(resp: requests.Response) -> bool:
    """EGW00201 초당 거래건수 초과 여부를 확인한다."""
    if resp.status_code != 500:
        return False
    try:
        return resp.json().get("msg_cd") == _RATE_LIMIT_CODE
    except Exception:
        return False


def _raise_for_error(resp: requests.Response, tr_id: str) -> None:
    """HTTP 오류 및 KIS API 비즈니스 오류를 통합 처리한다."""
    try:
        resp.raise_for_status()
    except requests.HTTPError as e:
        body = resp.content.decode("utf-8", errors="replace")[:300]
        raise requests.HTTPError(
            f"[{tr_id}] HTTP {resp.status_code}: {body}", response=resp
        ) from e

    data = resp.json()
    if data.get("rt_cd") not in ("0", None):
        raise RuntimeError(
            f"[{tr_id}] KIS API 오류 {data.get('msg_cd')}: {data.get('msg1')}"
        )


# ------------------------------------------------------------------
# 시세 조회
# ------------------------------------------------------------------

def get_current_price(stock_code: str) -> dict:
    """주식 현재가를 조회한다.

    Returns:
        {stock_code, current_price, change_rate, volume, open, high, low}
    """
    data = _get(
        "uapi/domestic-stock/v1/quotations/inquire-price",
        tr_id="FHKST01010100",
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
        },
    )
    output = data["output"]
    return {
        "stock_code":    stock_code,
        "current_price": int(output["stck_prpr"]),
        "change_rate":   float(output["prdy_ctrt"]),
        "volume":        int(output["acml_vol"]),
        "open":          int(output["stck_oprc"]),
        "high":          int(output["stck_hgpr"]),
        "low":           int(output["stck_lwpr"]),
    }


def get_ohlcv(stock_code: str, period: str = "D", count: int = 60) -> list[dict]:
    """일/주/월봉 OHLCV를 조회한다.

    Args:
        period: "D"(일봉), "W"(주봉), "M"(월봉)
        count:  반환할 최대 봉 수
    """
    end_dt   = datetime.now().strftime("%Y%m%d")
    start_dt = (datetime.now() - timedelta(days=count * 2)).strftime("%Y%m%d")

    data = _get(
        "uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
        tr_id="FHKST03010100",
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD":         stock_code,
            "FID_INPUT_DATE_1":       start_dt,
            "FID_INPUT_DATE_2":       end_dt,
            "FID_PERIOD_DIV_CODE":    period,
            "FID_ORG_ADJ_PRC":        "0",
        },
    )
    rows = []
    for item in data.get("output2", [])[:count]:
        rows.append({
            "date":   item["stck_bsop_date"],
            "open":   int(item["stck_oprc"]),
            "high":   int(item["stck_hgpr"]),
            "low":    int(item["stck_lwpr"]),
            "close":  int(item["stck_clpr"]),
            "volume": int(item["acml_vol"]),
        })
    return rows


def get_market_rank(market: str = "J", top_n: int = 30) -> list[dict]:
    """거래량 상위 종목을 조회한다.

    Args:
        market: "J"(KOSPI), "Q"(KOSDAQ)
        top_n:  반환할 종목 수
    """
    data = _get(
        "uapi/domestic-stock/v1/quotations/volume-rank",
        tr_id="FHPST01710000",
        params={
            "FID_COND_MRKT_DIV_CODE":  market,
            "FID_COND_SCR_DIV_CODE":   "20171",
            "FID_INPUT_ISCD":          "0000",
            "FID_DIV_CLS_CODE":        "0",
            "FID_BLNG_CLS_CODE":       "0",
            "FID_TRGT_CLS_CODE":       "111111111",
            "FID_TRGT_EXLS_CLS_CODE":  "000000",
            "FID_INPUT_PRICE_1":       "",
            "FID_INPUT_PRICE_2":       "",
            "FID_VOL_CNT":             "",
            "FID_INPUT_DATE_1":        "",
        },
    )
    result = []
    for item in data.get("output", [])[:top_n]:
        result.append({
            "stock_code":    item["mksc_shrn_iscd"],
            "stock_name":    item["hts_kor_isnm"],
            "current_price": int(item["stck_prpr"]),
            "change_rate":   float(item["prdy_ctrt"]),
            "volume":        int(item["acml_vol"]),
        })
    return result


# ------------------------------------------------------------------
# 계좌 조회
# ------------------------------------------------------------------

def get_balance() -> dict:
    """모의/실전 주식 잔고를 조회한다.

    Returns:
        {available_cash, total_eval, holdings: [{stock_code, stock_name,
        quantity, avg_price, current_price, profit_loss}]}
    """
    tr_id = "VTTC8434R" if settings.KIS_IS_VIRTUAL else "TTTC8434R"

    data = _get(
        "uapi/domestic-stock/v1/trading/inquire-balance",
        tr_id=tr_id,
        params={
            "CANO":                  settings.KIS_CANO,
            "ACNT_PRDT_CD":          settings.KIS_ACNT_PRDT_CD,
            "AFHR_FLPR_YN":          "N",
            "OFL_YN":                "N",
            "INQR_DVSN":             "02",
            "UNPR_DVSN":             "01",
            "FUND_STTL_ICLD_YN":     "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN":             "01",
            "CTX_AREA_FK100":        "",
            "CTX_AREA_NK100":        "",
        },
    )

    holdings = []
    for item in data.get("output1", []):
        qty = int(item.get("hldg_qty", 0))
        if qty > 0:
            holdings.append({
                "stock_code":    item["pdno"],
                "stock_name":    item["prdt_name"],
                "quantity":      qty,
                "avg_price":     float(item.get("pchs_avg_pric", 0)),
                "current_price": int(item.get("prpr", 0)),
                "profit_loss":   float(item.get("evlu_pfls_rt", 0)),
            })

    summary = data.get("output2", [{}])[0]
    return {
        "available_cash": int(summary.get("dnca_tot_amt", 0)),
        "total_eval":     int(summary.get("tot_evlu_amt", 0)),
        "holdings":       holdings,
    }


# ------------------------------------------------------------------
# 주문
# ------------------------------------------------------------------

def place_order(
    stock_code: str,
    order_type: str,
    quantity: int,
    price: int = 0,
) -> dict:
    """매수 또는 매도 주문을 실행한다.

    Args:
        order_type: "BUY" 또는 "SELL"
        price:      0이면 시장가, 그 외 지정가
    """
    if order_type == "BUY":
        tr_id = "VTTC0802U" if settings.KIS_IS_VIRTUAL else "TTTC0802U"
    else:
        tr_id = "VTTC0801U" if settings.KIS_IS_VIRTUAL else "TTTC0801U"

    ord_dvsn = "01" if price == 0 else "00"

    body = {
        "CANO":         settings.KIS_CANO,
        "ACNT_PRDT_CD": settings.KIS_ACNT_PRDT_CD,
        "PDNO":         stock_code,
        "ORD_DVSN":     ord_dvsn,
        "ORD_QTY":      str(quantity),
        "ORD_UNPR":     str(price),
    }

    data = _post("uapi/domestic-stock/v1/trading/order-cash", tr_id, body)
    order_no = data["output"]["ODNO"]
    logger.info(
        "%s 주문 완료 | %s %d주 | 주문번호: %s",
        order_type, stock_code, quantity, order_no,
    )
    return {
        "order_no":   order_no,
        "stock_code": stock_code,
        "order_type": order_type,
        "quantity":   quantity,
        "price":      price,
    }


def get_minute_ohlcv(stock_code: str, count: int = 40) -> list[dict]:
    """분봉 OHLCV를 조회한다 (TR_ID: FHKST03010200).

    Args:
        count: 반환할 최대 봉 수 (최신순)
    Returns:
        [{"time": "093000", "open": .., "high": .., "low": .., "close": .., "volume": ..}, ...]
        시간 오름차순 정렬 (오래된 것 → 최신)
    """
    now_str = datetime.now().strftime("%H%M%S")
    data = _get(
        "uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
        tr_id="FHKST03010200",
        params={
            "FID_ETC_CLS_CODE":        "0",   # 0=1분봉
            "FID_COND_MRKT_DIV_CODE":  "J",
            "FID_INPUT_ISCD":          stock_code,
            "FID_INPUT_HOUR_1":        now_str,
            "FID_PW_DATA_INCU_YN":     "Y",
        },
    )
    rows = []
    for item in data.get("output2", [])[:count]:
        rows.append({
            "date":   item.get("stck_cntg_hour", ""),  # indicators._to_df용 key
            "open":   int(item.get("stck_oprc", 0)),
            "high":   int(item.get("stck_hgpr", 0)),
            "low":    int(item.get("stck_lwpr", 0)),
            "close":  int(item.get("stck_prpr", 0)),
            "volume": int(item.get("cntg_vol", 0)),
        })
    # API는 최신순 반환 → 오름차순 정렬
    return list(reversed(rows))


def get_kospi_index() -> dict:
    """코스피 지수 현황을 조회한다. 실패 시 빈 dict 반환.

    Returns:
        {index: float, change_rate: float, change: float, volume: int}
    """
    try:
        data = _get(
            "uapi/domestic-stock/v1/quotations/inquire-index-price",
            tr_id="FHPUP02100000",
            params={
                "FID_COND_MRKT_DIV_CODE": "U",
                "FID_INPUT_ISCD":         "0001",
            },
        )
        out = data.get("output", {})
        return {
            "index":       float(out.get("bstp_nmix_prpr",      0.0)),  # 현재 지수
            "change":      float(out.get("bstp_nmix_prdy_vrss", 0.0)),  # 전일 대비
            "change_rate": float(out.get("bstp_nmix_prdy_ctrt", 0.0)),  # 등락률 %
            "volume":      int(  out.get("acml_vol",             0)),    # 누적 거래량
        }
    except Exception as e:
        logger.warning("코스피 지수 조회 실패: %s", e)
        return {}


def get_kospi_change_rate() -> float:
    """코스피 등락률(%)만 빠르게 반환한다. 실패 시 0.0."""
    return get_kospi_index().get("change_rate", 0.0)


def cancel_order(order_no: str, stock_code: str, quantity: int) -> dict:
    """주문을 취소한다."""
    tr_id = "VTTC0803U" if settings.KIS_IS_VIRTUAL else "TTTC0803U"
    body = {
        "CANO":                  settings.KIS_CANO,
        "ACNT_PRDT_CD":          settings.KIS_ACNT_PRDT_CD,
        "KRX_FWDG_ORD_ORGNO":   "",
        "ORGN_ODNO":             order_no,
        "ORD_DVSN":              "00",
        "RVSE_CNCL_DVSN_CD":    "02",
        "ORD_QTY":               str(quantity),
        "ORD_UNPR":              "0",
        "PDNO":                  stock_code,
        "QTY_ALL_ORD_YN":        "Y",
    }
    return _post("uapi/domestic-stock/v1/trading/order-rvsecncl", tr_id, body)
