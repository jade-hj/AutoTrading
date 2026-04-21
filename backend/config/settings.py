"""
시스템 전체 설정값 관리
Authentication_secret.txt 에서 API 키를 읽어옵니다.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

# ── KIS (한국투자증권) ──────────────────────────────────────────
KIS_APP_KEY    = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
KIS_CANO       = os.getenv("KIS_CANO", "")        # 계좌번호 앞 8자리
KIS_ACNT_PRDT_CD = os.getenv("KIS_ACNT_PRDT_CD", "01")  # 계좌 상품 코드

# 실전: https://openapi.koreainvestment.com:9443
# 모의: https://openapivts.koreainvestment.com:9443
KIS_BASE_URL   = os.getenv("KIS_BASE_URL", "https://openapivts.koreainvestment.com:9443")
KIS_IS_VIRTUAL = KIS_BASE_URL.startswith("https://openapivts")

# WebSocket
# 실전: ws://ops.koreainvestment.com:21000
# 모의: ws://ops.koreainvestment.com:31000
KIS_WS_URL     = os.getenv("KIS_WS_URL", "ws://ops.koreainvestment.com:31000")

# ── AI Agents ──────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY    = os.getenv("OPENAI_API_KEY", "")
GEMINI_API_KEY    = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY      = os.getenv("GROQ_API_KEY", "")

# 각 Agent에 사용할 모델
CLAUDE_MODEL = "claude-sonnet-4-6"
GPT_MODEL    = "gpt-4o-mini"
GEMINI_MODEL = "gemini-2.0-flash"

# Groq 모델 (OpenAI-compatible, 무료)
# 최신 지원 모델 목록: https://console.groq.com/docs/models
GROQ_MODEL_A = "llama-3.3-70b-versatile"   # Agent A (기술분석)
GROQ_MODEL_B = "qwen/qwen3-32b"            # Agent B (리스크관리)
GROQ_MODEL_C = "llama-3.1-8b-instant"      # Agent C (시장심리)

# ── 토론 설정 ──────────────────────────────────────────────────
DEBATE_ROUNDS = 2          # 토론 라운드 수 (1=개별 분석, 2=반론, 최종 투표)
MAX_TOKENS_PER_AGENT = 1500

# ── 종목 스캐닝 ────────────────────────────────────────────────
SCAN_MARKETS = ["KOSPI"]   # FHPST01710000 API: J(KOSPI)만 지원 — KOSDAQ(Q)는 모의투자 미지원
SCAN_TOP_N   = 10           # 스캔 후 Agent에게 넘길 후보 종목 수
SCAN_MIN_PRICE    = 5_000   # 최소 주가 (원)
SCAN_MIN_VOLUME   = 100_000 # 최소 거래량

# ── 매매 설정 ──────────────────────────────────────────────────
MAX_POSITION_RATIO = 0.20   # 종목당 최대 포트폴리오 비중 (20%)
STOP_LOSS_RATIO    = 0.05   # 손절 비율 (5%)
TAKE_PROFIT_RATIO  = 0.10   # 익절 비율 (10%)
ORDER_INTERVAL_SEC = 60     # 합의체 실행 주기 (초)

# ── 단타 설정 (공통) ───────────────────────────────────────────
# Agent 구성: FilterAgent(Llama-3.1-8b) → SignalAgent(Llama-3.3-70b) → RiskAgent(Qwen3-32b)
# AND 조건 파이프라인: 3단계 모두 통과해야 주문 실행
SCALPING_INTERVAL_SEC     = 300    # 5분 루프 (초)
SCALPING_CANDLE_COUNT     = 40     # 분봉 조회 수 (지표 계산용)
SCALPING_STOP_LOSS        = 0.005  # 손절 -0.5%
SCALPING_TAKE_PROFIT_1    = 0.008  # 1차 익절 +0.8% (절반 매도)
SCALPING_TAKE_PROFIT_2    = 0.015  # 2차 익절 +1.5% (전량 매도)
SCALPING_MAX_POSITIONS    = 3      # 최대 동시 보유 종목 수
SCALPING_POSITION_RATIO   = 0.20   # 종목당 최대 투자 비중
SCALPING_DAILY_LOSS_LIMIT = 0.03   # 일일 손실 한도 -3% (초과 시 당일 중지)
SCALPING_EXEC_START       = "09:30"  # 신규 진입 허용 시작
SCALPING_EXEC_END         = "14:50"  # 신규 진입 허용 종료
SCALPING_KOSPI_RANGE      = 0.003  # 코스피 ±0.3% 이내면 관망
SCALPING_MONITOR_SEC      = 30     # 포지션 모니터 주기 (초)
SCALPING_FORCE_CLOSE      = True   # 장 마감 전 미결 포지션 시장가 정리 여부
SCALPING_FORCE_CLOSE_TIME = "15:20"  # 강제 청산 시작 시각

# ── 단타 오전 모드 (09:30 ~ 11:59) ────────────────────────────
# 갭 상승 + 거래량 폭발 초기 포착 전략
# volume_ratio = 오늘 누적 거래량 / 직전 20일 평균 거래량
SCALPING_AM_END             = "11:59"  # 오전 모드 종료
SCALPING_AM_VOLUME_SURGE    = 1.5      # 거래량 급증 기준 (20일 평균 대비 1.5배)
SCALPING_AM_RSI_MIN         = 50       # RSI 진입 하한
SCALPING_AM_RSI_MAX         = 70       # RSI 진입 상한
SCALPING_AM_CHANGE_RATE_MAX = 25.0     # 등락률 상한 (상한가 근접 제외)
SCALPING_AM_GAP_LIMIT       = 0.02     # 시가 갭 ±2% 초과 종목 제외

# ── 단타 오후 모드 (12:00 ~ 14:50) ────────────────────────────
# 눌림목 반등 / 오후 새 테마 상승 초기 포착 전략
# 오전보다 완화된 기준 적용:
#   거래량 0.8x (오전 3.0x), RSI 40~70 (오전 50~70),
#   등락률 0.5~20% (오전 상한 25%만 제한), 갭 5% (오전 2%)
SCALPING_PM_START            = "12:00"  # 오후 모드 시작
SCALPING_PM_VOLUME_SURGE     = 0.8      # 거래량 기준 완화 (평균 대비 0.8배)
SCALPING_PM_RSI_MIN          = 40       # RSI 진입 하한 완화
SCALPING_PM_RSI_MAX          = 70       # RSI 진입 상한 완화
SCALPING_PM_CHANGE_RATE_MIN  = 0.5      # 등락률 하한 완화 (최소 모멘텀 확인)
SCALPING_PM_CHANGE_RATE_MAX  = 20.0     # 등락률 상한 완화 (상한가 근접만 제외)
SCALPING_PM_GAP_LIMIT        = 0.05     # 갭 필터 완화 (±5%)

# ── 로깅 ───────────────────────────────────────────────────────
LOG_DIR  = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
