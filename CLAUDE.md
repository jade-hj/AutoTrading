# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KRX(국내 주식) 실시간 자동 매매 시스템.
3개의 AI Agent(Llama, Qwen3, Llama-8b)가 토론 후 다수결로 종목 선정·매수·매도를 결정하고, KIS(한국투자증권) Open API로 주문을 실행한다.
모든 AI는 **Groq API**(무료, OpenAI-compatible)를 사용한다.

## Architecture

```
KIS WebSocket (실시간 시세)
        ↓
  MarketScanner (후보 종목 스캔)
        ↓
  ┌─────────────────────────────────┐
  │         AI Agent 합의체          │
  │  Round 1: 개별 분석 & 제안        │
  │  Round 2: 상호 반론              │
  │  Round 3: 최종 다수결 투표        │
  │  [ClaudeAgent / GPTAgent / GeminiAgent] │
  └─────────────────────────────────┘
        ↓ 매수/매도/홀드 + 종목
  OrderManager (KIS REST API)
        ↓
  PositionTracker / Logger
```

### 주요 모듈

| 경로 | 역할 |
|---|---|
| `config/settings.py` | 전체 설정값, API 키 로드 |
| `kis/auth.py` | KIS OAuth 토큰 발급·갱신 |
| `kis/rest_client.py` | 주문·잔고·시세 REST API |
| `kis/websocket_client.py` | 실시간 체결가 WebSocket |
| `data/market_scanner.py` | 후보 종목 스캔 (거래량·등락률 기준) |
| `data/indicators.py` | RSI, MACD, 이동평균 계산 |
| `agents/base_agent.py` | Agent 공통 인터페이스·데이터 구조 |
| `agents/claude_agent.py` | Agent A — Groq Llama-3.3-70b (기술분석) |
| `agents/gpt_agent.py` | Agent B — Groq Qwen3-32b (리스크관리) |
| `agents/gemini_agent.py` | Agent C — Groq Llama-3.1-8b (시장심리) |
| `agents/moderator.py` | 토론 진행 오케스트레이터 |
| `agents/consensus.py` | 다수결 집계 및 최종 결정 |
| `trading/order_manager.py` | 주문 실행 (매수/매도/취소) |
| `trading/position_tracker.py` | 보유 포지션·손익 추적 |
| `trading/portfolio.py` | 자금 배분·리스크 관리 |
| `utils/logger.py` | 거래 로그 (파일+콘솔) |
| `main.py` | 진입점, 이벤트 루프 |

### Agent 토론 흐름

1. **Round 1** — 각 Agent가 후보 종목 + 기술적 지표를 보고 독립적으로 `{action, stock_code, quantity_ratio, reasoning}` 제안
2. **Round 2** — 다른 두 Agent의 제안을 보고 동의/반론/수정
3. **최종 투표** — 각 Agent가 최종 `{action, stock_code}` 투표 → 2/3 합의 시 실행, 합의 실패 시 HOLD

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

| 변수 | 기본값 | 설명 |
|---|---|---|
| `SCAN_TOP_N` | 10 | Agent에 넘길 후보 종목 수 |
| `ORDER_INTERVAL_SEC` | 60 | 합의체 실행 주기 |
| `MAX_POSITION_RATIO` | 0.20 | 종목당 최대 비중 |
| `STOP_LOSS_RATIO` | 0.05 | 손절 기준 |
| `TAKE_PROFIT_RATIO` | 0.10 | 익절 기준 |
| `DEBATE_ROUNDS` | 2 | 토론 라운드 수 |
