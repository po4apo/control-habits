# Control Habits

Сервис трекинга дел и привычек: веб — настройка расписания и кнопок; Telegram-бот — пуши по расписанию и быстрые кнопки (старт/стоп интервалов).

## Требования

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) — менеджер пакетов и окружений

## Установка и запуск (локально)

```bash
# Клонирование и переход в каталог проекта
cd control-habits

# Установка зависимостей (при первом запуске создаётся uv.lock — его стоит закоммитить)
uv sync

# С dev-зависимостями (pytest, ruff и т.д.)
uv sync --all-extras

# Запуск API (FastAPI)
uv run uvicorn control_habits.api.app:app --reload

# Запуск бота (long polling + планировщик пушей)
uv run python -m control_habits.bot.run
```

Переменные окружения задаются в `.env` в корне проекта (см. `control_habits.config.Settings`). Для бота обязателен `BOT_TOKEN`.

## Разработка

- Линт: `uv run ruff check .`
- Тесты: `uv run pytest`
- Миграции БД: Alembic (см. `alembic.ini` и `src/control_habits/`)

Документация: папка `docs/` (план, требования, доменная модель, модули).
