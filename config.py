"""
Centralised configuration — single source of truth for all env vars.
---------------------------------------------------------------------
Uses pydantic-settings to validate, type-check, and document every
environment variable. All modules import `settings` from here instead
of calling os.environ / os.getenv directly.

Usage:
    from config import settings

    settings.composio_mcp_url    # str | None
    settings.composio_mcp_api_key # str | None
    settings.has_composio        # True if Composio MCP creds are set
    settings.has_telegram        # True if Telegram creds are set
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── OpenClaw Gateway ──────────────────────────────────────────
    openclaw_gateway_token: str | None = None
    openclaw_gateway_port: int = 18789
    openclaw_bridge_port: int = 18790
    openclaw_gateway_bind: str = "lan"
    openclaw_tz: str = "UTC"

    # ── Gemini API ────────────────────────────────────────────────
    gemini_api_key: str | None = None

    # ── Telegram ──────────────────────────────────────────────────
    telegram_bot_token: str | None = None
    telegram_chat_id: str | None = None

    # ── Meta Marketing API ────────────────────────────────────────
    meta_access_token: str | None = None
    meta_ad_account_id: str | None = None
    meta_adset_id: str = "YOUR_ADSET_ID"
    meta_page_id: str = "YOUR_PAGE_ID"

    # ── Composio (Google Ads via MCP) ─────────────────────────────
    composio_mcp_url: str | None = None
    composio_mcp_api_key: str | None = None

    # ── PostHog ─────────────────────────────────────────────────
    posthog_api_key: str | None = None
    posthog_host: str = "https://app.posthog.com"
    posthog_project_id: str | None = None

    # ── Derived helpers ───────────────────────────────────────────

    @property
    def has_gemini(self) -> bool:
        return self.gemini_api_key is not None

    @property
    def has_telegram(self) -> bool:
        return self.telegram_bot_token is not None and self.telegram_chat_id is not None

    @property
    def has_meta(self) -> bool:
        return self.meta_access_token is not None and self.meta_ad_account_id is not None

    @property
    def has_composio(self) -> bool:
        return self.composio_mcp_url is not None and self.composio_mcp_api_key is not None

    def require_composio(self) -> None:
        """Raise if Composio MCP credentials are not configured."""
        missing = []
        if not self.composio_mcp_url:
            missing.append("COMPOSIO_MCP_URL")
        if not self.composio_mcp_api_key:
            missing.append("COMPOSIO_MCP_API_KEY")
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Set them in .env or your shell."
            )

    @property
    def has_posthog(self) -> bool:
        return self.posthog_api_key is not None and self.posthog_project_id is not None

    def require_posthog(self) -> None:
        """Raise if PostHog credentials are not configured."""
        missing = []
        if not self.posthog_api_key:
            missing.append("POSTHOG_API_KEY")
        if not self.posthog_project_id:
            missing.append("POSTHOG_PROJECT_ID")
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Set them in .env or your shell."
            )

    def require_meta(self) -> None:
        """Raise if Meta API credentials are not configured."""
        missing = []
        if not self.meta_access_token:
            missing.append("META_ACCESS_TOKEN")
        if not self.meta_ad_account_id:
            missing.append("META_AD_ACCOUNT_ID")
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}. "
                "Set them in .env or your shell."
            )


settings = Settings()
