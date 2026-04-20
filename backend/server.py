"""
FastAPI 서버 진입점

  python server.py          — 기본 (포트 8000, reload 끄기)
  python server.py --reload — 개발 모드 (코드 변경 시 자동 재시작)
"""
import sys
import uvicorn

if __name__ == "__main__":
    reload = "--reload" in sys.argv
    uvicorn.run(
        "api.app:app",
        host    = "0.0.0.0",
        port    = 8000,
        reload  = reload,
        log_level = "info",
    )
