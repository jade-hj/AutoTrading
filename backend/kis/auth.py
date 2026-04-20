"""
KIS Open API - 인증 모듈

액세스 토큰과 WebSocket 접속키를 관리한다.
- 토큰은 .kis_token_cache 에 저장되어 프로세스 재시작 시 재사용된다.
- 만료 10분 전 자동 갱신한다.
"""

import json
import logging
import urllib3
from datetime import datetime, timedelta
from pathlib import Path

import requests

from config import settings

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

_TOKEN_CACHE_PATH = Path(__file__).resolve().parent.parent / ".kis_token_cache"


class KISAuth:
    def __init__(self):
        self._access_token: str = ""
        self._token_expires_at: datetime = datetime(2000, 1, 1)
        self._ws_approval_key: str = ""
        self._load_cache()

    # ------------------------------------------------------------------
    # 액세스 토큰
    # ------------------------------------------------------------------

    def get_access_token(self) -> str:
        """유효한 액세스 토큰을 반환한다. 만료 10분 전이면 재발급한다."""
        if datetime.now() >= self._token_expires_at - timedelta(minutes=10):
            self._issue_token()
        return self._access_token

    def _issue_token(self) -> None:
        url = f"{settings.KIS_BASE_URL}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey":     settings.KIS_APP_KEY,
            "appsecret":  settings.KIS_APP_SECRET,
        }
        resp = requests.post(url, json=body, timeout=10, verify=False)
        resp.raise_for_status()
        data = resp.json()

        if data.get("access_token") is None:
            raise RuntimeError(f"토큰 발급 실패: {data}")

        expires_in = int(data.get("expires_in", 86400))
        self._access_token = data["access_token"]
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
        self._save_cache()
        logger.info("KIS 액세스 토큰 발급 완료 (만료: %s)", self._token_expires_at.strftime("%Y-%m-%d %H:%M"))

    # ------------------------------------------------------------------
    # WebSocket 접속키
    # ------------------------------------------------------------------

    def get_ws_approval_key(self) -> str:
        """실시간 시세 WebSocket 접속 승인키를 반환한다."""
        if self._ws_approval_key:
            return self._ws_approval_key

        url = f"{settings.KIS_BASE_URL}/oauth2/Approval"
        body = {
            "grant_type": "client_credentials",
            "appkey":     settings.KIS_APP_KEY,
            "secretkey":  settings.KIS_APP_SECRET,
        }
        resp = requests.post(url, json=body, timeout=10, verify=False)
        resp.raise_for_status()
        self._ws_approval_key = resp.json()["approval_key"]
        logger.info("KIS WebSocket 접속키 발급 완료")
        return self._ws_approval_key

    # ------------------------------------------------------------------
    # 공통 요청 헤더
    # ------------------------------------------------------------------

    def get_headers(self, tr_id: str) -> dict:
        """KIS API 공통 요청 헤더를 반환한다."""
        return {
            "content-type":  "application/json; charset=utf-8",
            "authorization": f"Bearer {self.get_access_token()}",
            "appkey":        settings.KIS_APP_KEY,
            "appsecret":     settings.KIS_APP_SECRET,
            "tr_id":         tr_id,
            "tr_cont":       "",
            "custtype":      "P",
        }

    def get_headers_with_hashkey(self, tr_id: str, body: dict) -> dict:
        """POST 주문용 헤더 (hashkey 포함)를 반환한다."""
        headers = self.get_headers(tr_id)
        headers["hashkey"] = self._get_hashkey(body)
        return headers

    def _get_hashkey(self, body: dict) -> str:
        url = f"{settings.KIS_BASE_URL}/uapi/hashkey"
        headers = {
            "content-type": "application/json",
            "appkey":       settings.KIS_APP_KEY,
            "appsecret":    settings.KIS_APP_SECRET,
        }
        resp = requests.post(url, headers=headers, json=body, timeout=10, verify=False)
        resp.raise_for_status()
        return resp.json().get("HASH", "")

    # ------------------------------------------------------------------
    # 토큰 캐시
    # ------------------------------------------------------------------

    def _save_cache(self) -> None:
        try:
            _TOKEN_CACHE_PATH.write_text(
                json.dumps({
                    "access_token":     self._access_token,
                    "token_expires_at": self._token_expires_at.isoformat(),
                }),
                encoding="utf-8",
            )
        except OSError as e:
            logger.warning("토큰 캐시 저장 실패: %s", e)

    def _load_cache(self) -> None:
        try:
            if not _TOKEN_CACHE_PATH.exists():
                return
            data = json.loads(_TOKEN_CACHE_PATH.read_text(encoding="utf-8"))
            expires_at = datetime.fromisoformat(data["token_expires_at"])
            if datetime.now() < expires_at - timedelta(minutes=10):
                self._access_token = data["access_token"]
                self._token_expires_at = expires_at
                logger.info("캐시 토큰 재사용 (만료: %s)", expires_at.strftime("%Y-%m-%d %H:%M"))
        except (OSError, KeyError, ValueError) as e:
            logger.warning("토큰 캐시 로드 실패, 재발급 예정: %s", e)


# 싱글턴
_auth: KISAuth | None = None


def get_auth() -> KISAuth:
    global _auth
    if _auth is None:
        _auth = KISAuth()
    return _auth
