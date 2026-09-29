from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_mode: str = "DEMO"
    database_url: str = "sqlite:///./data/supportpilot.db"
    secret_key: str = "local-demo-only-change-before-deployment"
    cookie_secure: bool = False
    upload_root: Path = Path("./data/uploads")
    max_upload_bytes: int = 10 * 1024 * 1024
    reference_date: str = "2026-09-27"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    model_max_output_tokens: int = Field(default=700, ge=128, le=2000)
    model_max_input_chars: int = Field(default=16000, ge=4000, le=32000)
    model_max_passage_chars: int = Field(default=1000, ge=200, le=2000)
    commerce_adapter: str = "local"
    support_adapter: str = "local"
    shopify_api_version: str = "2026-07"
    shopify_shop_domain: str | None = None
    shopify_access_token: str | None = None
    zendesk_subdomain: str | None = None
    zendesk_email: str | None = None
    zendesk_api_token: str | None = None
    session_hours: int = 12

    @property
    def connected(self) -> bool:
        return self.app_mode.upper() == "CONNECTED"


settings = Settings()
