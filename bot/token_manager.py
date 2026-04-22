"""Tenant access token manager for Feishu API.

Provides a thread-safe singleton that acquires and auto-refreshes
the tenant_access_token. Never logs the token value itself.
"""
import logging
import threading
import time

import requests

from bot.config import APP_ID, APP_SECRET

logger = logging.getLogger(__name__)

TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
REFRESH_BEFORE_EXPIRY_SECONDS = 300  # refresh if less than 5 minutes remaining


class TokenManager:
    """Thread-safe tenant_access_token manager with auto-refresh."""

    def __init__(self) -> None:
        self._token: str = ""
        self._expires_at: float = 0.0  # Unix timestamp
        self._lock = threading.Lock()

    def get_token(self) -> str:
        """Return a valid tenant_access_token, refreshing if needed."""
        with self._lock:
            if self._should_refresh():
                self._refresh()
            return self._token

    def _should_refresh(self) -> bool:
        """Return True if token is missing or expiring within 5 minutes."""
        if not self._token:
            return True
        return time.time() >= (self._expires_at - REFRESH_BEFORE_EXPIRY_SECONDS)

    def _refresh(self) -> None:
        """Acquire a new tenant_access_token from Feishu API."""
        logger.info("Refreshing tenant_access_token...")
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
        logger.info("tenant_access_token refreshed, expires in %d seconds", expire_seconds)
        # NEVER log the token value itself


# Module-level singleton
token_manager = TokenManager()
