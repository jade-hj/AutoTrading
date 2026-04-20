# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KRX(국내 주식) 실시간 단타 자동 매매 시스템.
3개의 AI Agent(Llama-3.3-70b, Qwen3-32b, Llama-3.1-8b)가 각자 독립적 역할을 수행하고
**AND 조건 파이프라인**으로 최종 매수/매도를 결정한다.
모든 AI는 **Groq API**(무료, OpenAI-compatible)를 사용한다.

> **설계 변경 이력**: 기존 토론+다수결 방식 → 역할 기반 AND 조건 방식으로 전환
> - 토론 방식: 3 Agent가 Round 1(개별 분석) → Round 2(반론) → Round 3(투표 2/3 합의)
> - 현재 방식: FilterAgent → SignalAgent → RiskAgent 순차 실행, 모두 통과해야 주문

## Architecture

```
MarketScanner (KOSPI 거래량 상위 스캔)
        ↓ 후보 종목
  ┌─────────────────────────────────────────────────┐
  │  AND 조건 파이프라인 (ScalpingCoordinator)        │
  │                                                   │
  │  Step 1: FilterAgent (Llama-3.1-8b)              │
  │    — 시장 전체 상황 필터 (GO / NO-GO)             │
  │    — 오전/오후 모드별 규칙 체크 후 LLM 최종 판단  │
  │          ↓ GO                                     │
  │  Step 2: SignalAgent (Llama-3.3-70b)             │
  │    — 5분봉 기술지표 분석 (BUY / SELL / HOLD)      │
  │    — 오전: 4조건 중 3개↑, 오후: 4조건 중 2개↑    │
  │          ↓ BUY or SELL                            │
  │  Step 3: RiskAgent (Qwen3-32b)                   │
  │    — 포지션 사이징·손절/익절가 계산 (OK / REJECT)  │
  │          ↓ OK                                     │
  │  ✅ 주문 실행                                     │
  └─────────────────────────────────────────────────┘
        ↓
  KIS REST API (주문 실행)
        ↓
  PositionTracker (30초 주기 손절/익절 모니터)
```

### 오전/오후 모드 분리

| 항목 | 오전 모드 (09:30~11:59) | 오후 모드 (12:00~14:50) |
|---|---|---|
| 전략 | 거래량 급등 초기 포착 | 눌림목 반등 / 오후 신규 테마 |
| 거래량 기준 | 3.0x 이상 | 0.8x 이상 (완화) |
| RSI 범위 | 50~70 | 40~70 (하한 완화) |
| 등락률 | ~25% | 0.5~20% |
| 갭 필터 | ±2% | ±5% (완화) |
| SignalAgent BUY | 4조건 중 3개↑ | 4조건 중 2개↑ (완화) |

### 주요 모듈

| 경로 | 역할 |
|---|---|
| `config/settings.py` | 전체 설정값, API 키 로드 (`SCALPING_AM_*` / `SCALPING_PM_*`) |
| `kis/auth.py` | KIS OAuth 토큰 발급·갱신 |
| `kis/rest_client.py` | 주문·잔고·시세 REST API |
| `data/market_scanner.py` | 후보 종목 스캔 (거래량·등락률 기준) |
| `data/indicators.py` | RSI, MACD, 이동평균, 볼린저밴드 계산 |
| `agents/base_agent.py` | Agent 공통 데이터 구조 (ScalpingContext, *Decision) |
| `agents/filter_agent.py` | Model C — Llama-3.1-8b, 시장 필터 (오전/오후 모드) |
| `agents/signal_agent.py` | Model A — Llama-3.3-70b, 기술분석 신호 (오전/오후 모드) |
| `agents/risk_agent.py` | Model B — Qwen3-32b, 리스크 관리·포지션 사이징 |
| `agents/scalping_coordinator.py` | AND 조건 파이프라인 오케스트레이터 |
| `trading/position_tracker.py` | 보유 포지션 손절/익절 모니터 (30초 주기) |
| `utils/logger.py` | 거래 로그 (파일+콘솔, `trade_log.*`) |
| `main.py` | 진입점 — 5분 스캔 루프 + 30초 모니터 루프 병렬 실행 |

## Setup

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Credentials

`Authentication_secret.txt`(gitignored)에 아래 형식으로 API 키를 작성한다:

```
KIS_APP_KEY=...
KIS_APP_SECRET=...
KIS_CANO=...
KIS_ACNT_PRDT_CD=01
KIS_BASE_URL=https://openapivts.koreainvestment.com:29443  # 모의투자
KIS_WS_URL=ws://ops.koreainvestment.com:31000

GROQ_API_KEY=...        # https://console.groq.com
```

모의투자 → 실전 전환 시 `KIS_BASE_URL`과 `KIS_WS_URL`만 변경한다.

**Groq 모델 현황** (`config/settings.py`):
- `GROQ_MODEL_A`: `llama-3.3-70b-versatile` (Agent A)
- `GROQ_MODEL_B`: `qwen/qwen3-32b` (Agent B) — `<think>` CoT 블록 자동 제거
- `GROQ_MODEL_C`: `llama-3.1-8b-instant` (Agent C)

Groq 지원 모델은 자주 변경됨. 폐기 시 `python -c "from openai import OpenAI; from config import settings; [print(m.id) for m in OpenAI(api_key=settings.GROQ_API_KEY, base_url='https://api.groq.com/openai/v1').models.list().data]"` 로 확인.

## Commands

```bash
# 실행
python main.py

# 테스트
pytest

# 단일 테스트
pytest tests/test_consensus.py::test_majority_vote
```

## Key Settings (`config/settings.py`)

**공통 단타 설정**

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SCALPING_INTERVAL_SEC` | 300 | 스캔 주기 (5분) |
| `SCALPING_MAX_POSITIONS` | 3 | 최대 동시 보유 종목 |
| `SCALPING_STOP_LOSS` | 0.005 | 손절 -0.5% |
| `SCALPING_TAKE_PROFIT_1` | 0.008 | 1차 익절 +0.8% (절반 매도) |
| `SCALPING_TAKE_PROFIT_2` | 0.015 | 2차 익절 +1.5% (전량 매도) |
| `SCALPING_KOSPI_RANGE` | 0.003 | 코스피 ±0.3% 이내 → 관망 |

**오전 모드 (`SCALPING_AM_*`)**

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SCALPING_AM_VOLUME_SURGE` | 3.0 | 거래량 배수 기준 |
| `SCALPING_AM_RSI_MIN/MAX` | 50 / 70 | RSI 진입 범위 |
| `SCALPING_AM_CHANGE_RATE_MAX` | 25.0 | 등락률 상한 |
| `SCALPING_AM_GAP_LIMIT` | 0.02 | 갭 필터 ±2% |

**오후 모드 (`SCALPING_PM_*`)**

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SCALPING_PM_VOLUME_SURGE` | 0.8 | 거래량 배수 기준 (완화) |
| `SCALPING_PM_RSI_MIN/MAX` | 40 / 70 | RSI 진입 범위 (하한 완화) |
| `SCALPING_PM_CHANGE_RATE_MIN/MAX` | 0.5 / 20.0 | 등락률 범위 |
| `SCALPING_PM_GAP_LIMIT` | 0.05 | 갭 필터 ±5% (완화) |
