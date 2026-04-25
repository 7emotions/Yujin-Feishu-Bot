import threading
import time

import requests

from adapters.feishu.settings import APP_ID, APP_SECRET

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
REFRESH_BEFORE_EXPIRY_SECONDS = 300


class TokenManager:
    def __init__(self) -> None:
        self._token: str = ""
        self._expires_at: float = 0.0
        self._lock = threading.Lock()

    def get_token(self) -> str:
        with self._lock:
            if self._should_refresh():
                self._refresh()
            return self._token

    def _should_refresh(self) -> bool:
        if not self._token:
            return True
        return time.time() >= (self._expires_at - REFRESH_BEFORE_EXPIRY_SECONDS)

    def _refresh(self) -> None:
        response = requests.post(
            TOKEN_URL,
            json={"app_id": APP_ID, "app_secret": APP_SECRET},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        if data.get("code") != 0:
            raise RuntimeError(f"Failed to get tenant_access_token: {data.get('msg')}")
        self._token = data["tenant_access_token"]
        expire_seconds = data.get("expire", 7200)
        self._expires_at = time.time() + expire_seconds


token_manager = TokenManager()
