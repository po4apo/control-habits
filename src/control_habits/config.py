"""Конфигурация приложения (переменные окружения)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень проекта (где лежит .env и pyproject.toml) — чтобы бот и API находили .env при любом cwd
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """Настройки из окружения."""

    model_config = SettingsConfigDict(
        env_file=(_PROJECT_ROOT / ".env").resolve(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "postgresql+psycopg://localhost/control_habits"
    """Строка подключения к PostgreSQL."""

    bot_username: str = "Po4aPo_bot"
    """Имя бота в Telegram (без @) для ссылки t.me/<bot_username>?start=<code>."""

    bot_token: str = ""
    """Токен бота Telegram (для процесса бота). Задаётся через окружение (BOT_TOKEN)."""

    web_app_url: str = ""
    """URL веб-приложения для текста онбординга в боте (например https://app.example.com)."""

    scheduler_interval_seconds: int = 60
    """Интервал тика планировщика пушей (секунды)."""