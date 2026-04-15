# Деплой на прод (Docker Compose)

Прод — внешняя Linux-машина с **Docker** и **`docker-compose`** (команда через дефис). Образы API и бота собираются в GitHub Actions и публикуются в GitHub Container Registry (ghcr.io).

## Образы

- **API**: `ghcr.io/<owner>/control-habits-api:<tag>`
- **Бот**: `ghcr.io/<owner>/control-habits-bot:<tag>`

Тег задаётся вручную при релизе (например `v0.1.0`) или `latest` при пуше в `main`. См. [CI/CD](ci-cd.md).

## Деплой полного стека на Ubuntu (API + bot + PostgreSQL в контейнере)

Выкладка на хост по SSH делается **только** двумя ручными workflow в GitHub Actions (других поддерживаемых сценариев SSH-деплоя нет).

| Порядок | Workflow | Файл |
|---------|----------|------|
| 1. Первый раз | **Первичный деплой на хост (SSH)** | [.github/workflows/ssh-host-bootstrap.yml](../../.github/workflows/ssh-host-bootstrap.yml) |
| 2. Обновление версии | **Обновление стека (SSH)** | [.github/workflows/manual-deploy-ssh.yml](../../.github/workflows/manual-deploy-ssh.yml) |

**На сервере до запуска:** установлены `docker` и `docker-compose` в `PATH`; рекомендуемый каталог — в home пользователя SSH, например `/home/ubuntu/control-habits-deploy` (**без** `~` в параметрах Actions).

**Повторный bootstrap** на тот же `remote_path` заново зальёт [docker-compose.full.yml](../../docker-compose.full.yml) и перезапишет **`.env`** с раннера. Для смены только тега образов используй **Обновление стека (SSH)**.

### Секреты репозитория (GitHub → Settings → Secrets and variables → Actions)

| Секрет | Bootstrap | Обновление стека |
|--------|-----------|------------------|
| `DEPLOY_SSH_PRIVATE_KEY` | да | да |
| `DEPLOY_ENV` | да (многострочное содержимое будущего `.env` на сервере) | нет |
| `GHCR_USERNAME` | если нужен `docker login` (образы приватные) | если нужен `docker login` перед `pull` |
| `GHCR_TOKEN` | PAT с `read:packages` | то же |

Если задан `GHCR_TOKEN`, должен быть задан и `GHCR_USERNAME` (логин GitHub или org, как при ручном `docker login ghcr.io`).

### Содержимое `DEPLOY_ENV` и файла `.env` на сервере

Не коммить прод-`.env` в репозиторий. В секрет `DEPLOY_ENV` вставь тот же текст, что должен оказаться в `.env` на хосте (переносы строк как в файле).

| Переменная | Описание |
|------------|----------|
| `IMAGE_OWNER` | GitHub user/org для образов ghcr (как владелец репозитория) |
| `COMPOSE_IMAGE_TAG` | Можно задать в `.env`; при деплое workflow также выставляет `COMPOSE_IMAGE_TAG` из поля формы и это перекрывает значение для сеанса `docker-compose` |
| `DATABASE_URL` | Для [docker-compose.full.yml](../../docker-compose.full.yml) по умолчанию строка на сервис `db` в compose |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | Учётка БД в контейнере; при смене пароля задай согласованный `DATABASE_URL` |
| `BOT_TOKEN` | Токен Telegram-бота |
| `BOT_USERNAME`, `WEB_APP_URL` | По необходимости |

Данные PostgreSQL в full-стеке хранятся в volume `pgdata`.

### Локальная разработка (не прод)

Из корня репозитория:

```bash
docker-compose up -d

docker-compose logs -f api bot
```

Создай `.env` с `BOT_TOKEN`. Сборка образов локально — см. [docker-compose.yml](../../docker-compose.yml).

## Прод: внешняя БД (без контейнера postgres)

Если PostgreSQL **не** в Docker на том же хосте, используй [docker-compose.prod.yml](../../docker-compose.prod.yml): в `.env` укажи `DATABASE_URL`, `IMAGE_OWNER`, `COMPOSE_IMAGE_TAG`, `BOT_TOKEN`. Запуск на сервере вручную:

```bash
docker-compose -f docker-compose.prod.yml pull
docker-compose -f docker-compose.prod.yml up -d
```

Описанные выше **два SSH workflow** рассчитаны на [docker-compose.full.yml](../../docker-compose.full.yml) с БД в контейнере.

## Миграции Alembic

Workflow **Первичный деплой** и **Обновление стека** после `up` выполняют `docker-compose … run --rm api uv run alembic upgrade head`.

Ручной запуск на сервере при необходимости:

```bash
docker-compose -f docker-compose.full.yml run --rm api uv run alembic upgrade head
```

Для стека только с `docker-compose.prod.yml` подставь свой `-f` и тот же `DATABASE_URL`, что у контейнеров.
