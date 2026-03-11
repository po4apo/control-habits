# Control Habits — команды для разработки и запуска
# Используется uv для запуска (uv run ...).

.PHONY: bot server migrate migrate-down test help

help:
	@echo "Доступные команды:"
	@echo "  make bot         — запуск Telegram-бота (long polling)"
	@echo "  make server     — запуск API-сервера (uvicorn, с перезагрузкой)"
	@echo "  make migrate    — применить миграции БД (alembic upgrade head)"
	@echo "  make migrate-down — откатить последнюю миграцию"
	@echo "  make test       — запуск тестов (pytest)"
	@echo ""
	@echo "Перед первым запуском бота или сервера выполните: make migrate"

bot:
	uv run python -m control_habits.bot.run

server:
	uv run uvicorn control_habits.api.app:app --host 0.0.0.0 --port 8000 --reload

migrate:
	uv run alembic upgrade head

migrate-down:
	uv run alembic downgrade -1

test:
	uv run pytest tests/ -v
