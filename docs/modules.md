# Разбиение на компоненты (для вайбкодинга)

Модули спроектированы так, чтобы каждый можно было реализовать отдельно, с чёткими входами и выходами и ограниченным контекстом для реализации с помощью ИИ.

## 1. auth_linking (связка сайта и Telegram)

**Назначение**: выдача одноразового кода привязки и потребление кода при `/start` в боте.

**Входы**:
- `create_link_code(web_session_id: str, ttl_seconds: int = 600) -> str`  
  Возвращает код (только символы A–Z, a–z, 0–9, `_`, `-`). Сохраняет в БД/кэш с `expires_at`.

- `consume_link_code(code: str, telegram_user_id: int) -> int | None`  
  Если код валиден, не истёк и не использован: помечает использованным, связывает с `telegram_user_id`, создаёт/возвращает `user_id`. Иначе `None`.

**Выход/инварианты**: TTL кода; один код — одно потребление; при consume возвращаем один и тот же `user_id` при повторном вызове с тем же кодом (идемпотентность по коду после первого успеха не требуется, код уже consumed).

**Зависимости**: хранилище (LinkCodesRepo, UsersRepo).

---

## 2. schedule_model (домен расписаний)

**Назначение**: модели и развёртка шаблона в «план на дату».

**DTO/модели**:
- `TaskItem`, `EventItem` (kind, title, start_time, end_time, days_of_week, activity_id?).
- `ScheduleTemplate`, `DayOfWeek` (enum или битмаска).
- `PlannedItem`: элемент, развёрнутый на конкретную дату (plan_item_id, date, planned_at для старта/конца, type: task | event_start | event_end).

**Входы**:
- `expand_template(user_id: int, date: date) -> list[PlannedItem]`  
  По шаблону пользователя и дням недели возвращает список запланированных элементов на эту дату с вычисленными UTC-временами (с учётом timezone пользователя).

**Зависимости**: ScheduleRepo, UsersRepo (timezone).

---

## 3. planning_engine (что и когда пушить)

**Назначение**: по развёрнутому плану и настройкам пользователя формировать список «задач на отправку» с ключом идемпотентности.

**Входы**:
- `build_notification_jobs(user_id: int, date: date) -> list[NotificationJob]`  
  Использует `expand_template`; для каждого элемента создаёт запись/объект NotificationJob: `planned_at` (UTC), `type`, `plan_item_id`, `idempotency_key`, текст/данные для сообщения.

**Типы**: `task_prompt`, `event_start`, `event_end`.

**Выход**: список `NotificationJob` (или сохранение в таблицу `notifications` с `sent_at = NULL`). Ключ идемпотентности однозначно определяет один пуш (например, `plan_item_id + date + type`).

**Зависимости**: schedule_model, ScheduleRepo, NotificationsRepo.

---

## 4. bot_messages (рендер сообщений и клавиатур)

**Назначение**: формирование текста и разметки кнопок для Telegram.

**Входы**:
- `build_task_prompt(task_planned: PlannedItem) -> (text: str, reply_markup)`  
  Текст: «Сделал [title]?»; кнопки: Сделал / Не сделал / Пропустить (callback_data укладывается в 64 байта).

- `build_event_start_prompt(event_planned: PlannedItem) -> (text, reply_markup)`  
  Текст: «Начал [title]?»; кнопки: Начал / Не начал.

- `build_event_end_prompt(event_planned: PlannedItem) -> (text, reply_markup)`  
  Текст: «Закончил [title]?»; кнопки: Закончил / Пропустил.

- `build_hotkeys_keyboard(user_id: int) -> ReplyKeyboardMarkup | InlineKeyboardMarkup`  
  Список hotkey-кнопок пользователя (из HotkeysRepo/ActivityRepo); подписи и callback_data или данные для reply-клавиатуры.

- `build_active_sessions_message(sessions: list[ActiveSession]) -> str`  
  Текст списка: например, «Сейчас идёт: YouTube с 14:30; Работа с 09:00».

- `build_finish_buttons(sessions: list[ActiveSession]) -> InlineKeyboardMarkup`  
  По одной кнопке «Закончить [название]» на каждую сессию; callback_data содержит session_id или пару (user_id, activity_id) в пределах 64 байт.

**Зависимости**: модели PlannedItem, ActiveSession; при сборке callback — знание формата payload (короткие префиксы + id).

---

## 5. bot_handlers (обработка ответов и команд)

**Назначение**: обработка входящих апдейтов — callback от пушей, нажатия hotkey, команда `/active`, `/start`.

**Входы** (концептуально):
- Апдейт: `Update` (aiogram) или эквивалент (callback_query, message).
- Для callback: разбор `callback_data` (тип + id/ключ идемпотентности).

**Логика**:
- Ответ на пуш: проверка идемпотентности по ключу; запись LogEntry с `responded_at=now()`; обновление сообщения; `answer_callback_query`.
- Hotkey: вызов hotkey_sessions.start_session / stop_session; запись LogEntry; ответ пользователю.
- `/active`: вызов hotkey_sessions.list_active_sessions; build_active_sessions_message + build_finish_buttons; отправка сообщения.
- `/start <code>`: вызов auth_linking.consume_link_code; ответ в чат.

**Выход**: побочные эффекты (запись в БД, отправка/редактирование сообщений). Без дублей при повторном callback (идемпотентность).

**Зависимости**: auth_linking, hotkey_sessions, storage (LogsRepo, NotificationsRepo), bot_messages.

---

## 6. hotkey_sessions (интервалы по кнопкам)

**Назначение**: старт/стоп сессии и список активных.

**Входы**:
- `start_session(user_id: int, activity_id: int, now: datetime) -> int`  
  Создаёт запись ActiveSession, возвращает session_id. Если уже есть активная по этой активности — можно вернуть существующий id или считать идемпотентным «повторный старт» (зависит от продукта).

- `stop_session(user_id: int, activity_id: int, now: datetime) -> float | None`  
  Устанавливает `ended_at = now` у активной сессии, возвращает длительность в секундах. Если активной нет — возврат None (идемпотентно).

- `list_active_sessions(user_id: int) -> list[ActiveSession]`  
  Все сессии пользователя с `ended_at IS NULL`, с подгрузкой названий активностей.

**Инварианты**: одна активная сессия на пару (user_id, activity_id).

**Зависимости**: SessionsRepo, ActivityRepo.

---

## 7. reporting (отчёты)

**Назначение**: агрегация данных за день для веб-отчёта.

**Входы**:
- `get_daily_report(user_id: int, date: date) -> DailyReport`  
  Структура: список запланированного (planned items + типы), список фактов ответов (LogEntry с временем и статусом), список интервалов (сессии с started_at/ended_at за эту дату, длительности).

**Зависимости**: ScheduleRepo (или schedule_model.expand_template), LogsRepo, SessionsRepo (или слой, возвращающий закрытые сессии за дату).

---

## 8. storage (репозитории)

**Назначение**: доступ к БД через репозитории, без бизнес-логики.

**Репозитории** (интерфейсы или конкретные классы):
- **UsersRepo**: get_by_telegram_id, get_by_id, create, update timezone.
- **LinkCodesRepo**: create, get_by_code, mark_consumed.
- **ScheduleRepo**: get_template, get_plan_items, list_by_user.
- **ActivityRepo**: list_by_user, get_by_id, create.
- **HotkeysRepo**: list_by_user, add, remove, reorder.
- **NotificationsRepo**: create_many, get_pending(planned_at <= until), mark_sent.
- **LogsRepo**: add, exists_by_idempotency_key (или по notification_id).
- **SessionsRepo**: create, get_active(user_id, activity_id), list_active(user_id), close(session_id, ended_at).

Все даты/времена на границе репозиториев — в UTC.

---

## 9. Порядок реализации (рекомендуемый)

1. **storage** — модели SQLAlchemy, миграции, репозитории.
2. **auth_linking** — создание/потребление кода, интеграция с ботом и веб-API.
3. **schedule_model** — развёртка шаблона на дату.
4. **planning_engine** — формирование NotificationJob / записей в notifications.
5. **bot_messages** — все сборщики текста и клавиатур (с учётом лимита 64 байта).
6. **hotkey_sessions** — старт/стоп/список.
7. **bot_handlers** — роутинг апдейтов и вызов перечисленных модулей.
8. **reporting** — отчёт за день.
9. Scheduler — цикл/APScheduler, выборка pending и отправка через Bot API и bot_messages.

Каждый модуль можно тестировать изолированно (моки соседних слоёв).

## 10. Ссылки

- Системный дизайн: [system-design.md](system-design.md).
- Доменная модель: [domain-model.md](domain-model.md).
- Требования: [requirements.md](requirements.md).
