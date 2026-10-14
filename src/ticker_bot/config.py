from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ConfigurationError(ValueError):
    """Raised when environment configuration is invalid."""


def _parse_bool(name: str, value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} має бути true або false")


def _parse_chat_ids(value: str) -> frozenset[int]:
    if not value.strip():
        return frozenset()

    result: set[int] = set()
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            result.add(int(item))
        except ValueError as exc:
            raise ConfigurationError("ALLOWED_CHAT_IDS має містити числові ID через кому") from exc
    return frozenset(result)


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_bot_token: str | None
    bot_enabled: bool
    allowed_chat_ids: frozenset[int]
    app_timezone: ZoneInfo
    database_path: Path
    enable_plain_tickers: bool
    api_host: str
    api_port: int
    scanner_api_token: str | None
    scanner_site_password: str | None
    log_level: str
    local_settings_path: Path | None = None

    @classmethod
    def from_env(cls) -> Settings:
        bot_enabled = _parse_bool("BOT_ENABLED", os.getenv("BOT_ENABLED", "true"))
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or None
        if bot_enabled and token is None:
            raise ConfigurationError(
                "Не задано TELEGRAM_BOT_TOKEN. Додайте токен або встановіть BOT_ENABLED=false."
            )

        timezone_name = os.getenv("APP_TIMEZONE", "America/New_York").strip()
        try:
            timezone = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ConfigurationError(f"Невідомий часовий пояс: {timezone_name}") from exc

        try:
            api_port = int(os.getenv("API_PORT", "8000"))
        except ValueError as exc:
            raise ConfigurationError("API_PORT має бути числом") from exc
        if not 1 <= api_port <= 65535:
            raise ConfigurationError("API_PORT має бути від 1 до 65535")

        database_path = Path(os.getenv("DATABASE_PATH", "data/tickers.db")).expanduser()
        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ConfigurationError("Некоректний LOG_LEVEL")

        return cls(
            telegram_bot_token=token,
            bot_enabled=bot_enabled,
            allowed_chat_ids=_parse_chat_ids(os.getenv("ALLOWED_CHAT_IDS", "")),
            app_timezone=timezone,
            database_path=database_path,
            enable_plain_tickers=_parse_bool(
                "ENABLE_PLAIN_TICKERS", os.getenv("ENABLE_PLAIN_TICKERS", "true")
            ),
            api_host=os.getenv("API_HOST", "127.0.0.1").strip() or "127.0.0.1",
            api_port=api_port,
            scanner_api_token=os.getenv("SCANNER_API_TOKEN", "").strip() or None,
            scanner_site_password=os.getenv("SCANNER_SITE_PASSWORD", "").strip() or None,
            log_level=log_level,
            local_settings_path=(
                Path(value).expanduser()
                if (value := os.getenv("LOCAL_SETTINGS_PATH", "").strip())
                else None
            ),
        )

    def chat_is_allowed(self, chat_id: int) -> bool:
        return not self.allowed_chat_ids or chat_id in self.allowed_chat_ids
