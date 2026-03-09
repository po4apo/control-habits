# Деплой на прод (Docker Compose)

Прод — внешняя Linux-машина с установленными Docker и Docker Compose. Образы API и бота собираются в GitHub Actions и публикуются в GitHub Container Registry (ghcr.io).

## Образы

- **API**: `ghcr.io/<owner>/control-habits-api:<tag>`
- **Бот**: `ghcr.io/<owner>/control-habits-bot:<tag>`

Тег задаётся вручную при релизе (например `v0.1.0`) или `latest` при пуше в `main`. См. [CI/CD](ci-cd.md).

## Секреты и переменные окружения

Не хранить в репозитории и не коммитить `.env` с прод-данными. На сервере задать переменные в `.env` или через окружение:

| Переменная | Описание |
|------------|----------|
| `DATABASE_URL` | Строка подключения к PostgreSQL (например `postgresql+psycopg://user:pass@host:5432/control_habits`) |
| `BOT_TOKEN` | Токен Telegram-бота (обязателен для контейнера bot) |
| `BOT_USERNAME` | Имя бота без @ (для ссылки t.me) |
| `WEB_APP_URL` | URL веб-приложения для онбординга (опционально) |

Для GHCR: на проде при использовании образов из приватного registry выполнить вход, например `docker login ghcr.io -u <user> -p <token>` (токен с правом `read:packages`).

## Запуск с локальной БД (dev/демо)

Из корня репозитория:

```bash
# Сборка и запуск api, bot и postgres
docker compose up -d

# Логи
docker compose logs -f api bot
```

По умолчанию `DATABASE_URL` указывает на сервис `db` в compose. Создать `.env` с `BOT_TOKEN` (и при необходимости переопределить остальное).

## Прод: внешняя БД

Если PostgreSQL уже развёрнут на хосте или отдельном сервере:

1. Задать `DATABASE_URL` в `.env` на проде (указать хост, порт, пользователя, пароль, БД).
2. Запускать только сервисы api и bot (без контейнера БД):

   ```bash
   docker compose up -d api bot
   ```

Используйте [docker-compose.prod.yml](../../docker-compose.prod.yml): в нём только сервисы `api` и `bot`, без БД. В `.env` задайте `IMAGE_OWNER` (ваш GitHub org/user), `COMPOSE_IMAGE_TAG` (например `v0.1.0`), `DATABASE_URL`, `BOT_TOKEN`. Запуск: `docker compose -f docker-compose.prod.yml up -d`.

## Прод: образы из ghcr.io по тегу релиза

На проде образы берутся из registry с тегом версии (например `v0.1.0`). В `.env` задайте `IMAGE_OWNER` (ваш GitHub org/user) и `COMPOSE_IMAGE_TAG=v0.1.0`. При использовании [docker-compose.prod.yml](../../docker-compose.prod.yml):

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

## Миграции Alembic

Схема БД обновляется через Alembic. При деплое миграции нужно применить до или сразу после запуска новых контейнеров.

**Вариант 1 — один раз перед/после деплоя (рекомендуется):**

На сервере (или с машины, имеющей доступ к прод-БД) выполнить миграции в контексте приложения, например в временном контейнере API с тем же `DATABASE_URL`:

```bash
docker compose run --rm api uv run alembic upgrade head
```

Либо установить Alembic локально, задать `DATABASE_URL` и выполнить `alembic upgrade head` из корня репозитория (где есть `alembic.ini`). Убедиться, что `alembic.ini` и `env.py` настроены на использование переменной окружения для БД.

**Вариант 2 — в entrypoint контейнера API:** при старте API перед uvicorn вызывать `alembic upgrade head`. Требует правки образа/скрипта старта (отдельный скрипт или entrypoint).

Итог: перед или после `docker compose up` один раз выполнить `alembic upgrade head` с продовым `DATABASE_URL`.
