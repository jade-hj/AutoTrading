"""
기술적 지표 계산 모듈

OHLCV 데이터(list[dict])를 받아 RSI, MACD, 이동평균, 볼린저밴드를 계산한다.
"""
import pandas as pd
import numpy as np


def _to_df(ohlcv: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(ohlcv)
    df = df.sort_values("date").reset_index(drop=True)
    df["close"]  = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    return df


def calc_rsi(ohlcv: list[dict], period: int = 14) -> float:
    """RSI (0~100). 데이터 부족 시 -1 반환"""
    df = _to_df(ohlcv)
    if len(df) < period + 1:
        return -1.0
    delta  = df["close"].diff()
    gain   = delta.clip(lower=0).ewm(com=period - 1, adjust=False).mean()
    loss   = (-delta.clip(upper=0)).ewm(com=period - 1, adjust=False).mean()
    rs     = gain / loss.replace(0, np.nan)
    rsi    = (100 - 100 / (1 + rs)).iloc[-1]
    return round(float(rsi), 2)


def calc_macd(
    ohlcv: list[dict],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict:
    """
    MACD 반환값:
      macd, signal, histogram, crossover (True = 골든크로스)
    """
    df = _to_df(ohlcv)
    if len(df) < slow + signal:
        return {"macd": 0.0, "signal": 0.0, "histogram": 0.0, "crossover": False}

    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd_line   = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram   = macd_line - signal_line

    crossover = (
        macd_line.iloc[-1] > signal_line.iloc[-1]
        and macd_line.iloc[-2] <= signal_line.iloc[-2]
    )
    return {
        "macd":      round(float(macd_line.iloc[-1]), 4),
        "signal":    round(float(signal_line.iloc[-1]), 4),
        "histogram": round(float(histogram.iloc[-1]), 4),
        "crossover": crossover,
    }


def calc_moving_averages(ohlcv: list[dict]) -> dict:
    """5/20/60/120일 이동평균 및 정배열 여부"""
    df   = _to_df(ohlcv)
    close = df["close"]
    result = {}
    for period in [5, 20, 60, 120]:
        if len(close) >= period:
            result[f"ma{period}"] = round(float(close.rolling(period).mean().iloc[-1]), 2)
        else:
            result[f"ma{period}"] = None

    # 정배열: ma5 > ma20 > ma60
    vals = [result.get(f"ma{p}") for p in [5, 20, 60]]
    result["uptrend"] = all(
        v is not None and vals[i + 1] is not None and v > vals[i + 1]
        for i, v in enumerate(vals[:-1])
    )
    return result


def calc_bollinger(ohlcv: list[dict], period: int = 20, std: float = 2.0) -> dict:
    """볼린저밴드 — upper, middle, lower, bandwidth, %B"""
    df = _to_df(ohlcv)
    if len(df) < period:
        return {}
    close  = df["close"]
    middle = close.rolling(period).mean().iloc[-1]
    std_v  = close.rolling(period).std().iloc[-1]
    upper  = middle + std * std_v
    lower  = middle - std * std_v
    current = close.iloc[-1]
    bandwidth = (upper - lower) / middle * 100
    percent_b = (current - lower) / (upper - lower) if upper != lower else 0.5
    return {
        "upper":       round(float(upper), 2),
        "middle":      round(float(middle), 2),
        "lower":       round(float(lower), 2),
        "bandwidth":   round(float(bandwidth), 2),
        "percent_b":   round(float(percent_b), 4),
    }


def get_all_indicators(ohlcv: list[dict]) -> dict:
    """모든 지표를 한번에 계산해 반환"""
    return {
        "rsi":     calc_rsi(ohlcv),
        "macd":    calc_macd(ohlcv),
        "ma":      calc_moving_averages(ohlcv),
        "bollinger": calc_bollinger(ohlcv),
    }
