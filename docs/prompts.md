# Промпты по подзадачам (Control Habits)

Готовые формулировки для чата или под-агента. Использовать по порядку модулей; перед запуском убедиться, что зависимости уже реализованы. Контекст проекта: `plan.md`, `docs/` (особенно `docs/modules.md`, `docs/system-design.md`, `docs/requirements.md`).

---

## 1. Storage

### 1.1 Модели БД и миграция

```
По docs/modules.md (раздел 8) и docs/system-design.md (раздел 4) реализуй слой хранилища проекта control-habits.

Подзадача: модели SQLAlchemy 2.x и первая миграция Alembic.

Таблицы по спеце: users, link_codes, activities, hotkeys, schedule_templates, plan_items, notifications, log_entries, active_sessions — поля как в system-design.md. Все даты/времена в БД — UTC. Индексы: telegram_user_id, user_id в связанных таблицах; planned_at, sent_at, idempotency_key; (user_id, activity_id, ended_at) для active_sessions.

Стек: Python, SQLAlchemy 2.x, Alembic, PostgreSQL. Код в src/ (или уточни структуру репо). Не добавляй бизнес-логику и API — только модели и миграцию.
```

### 1.2 Репозитории

```
По docs/modules.md (раздел 8) реализуй репозитории для проекта control-habits. Модели и миграции уже есть.

Репозитории: UsersRepo (get_by_telegram_id, get_by_id, create, update timezone), LinkCodesRepo (create, get_by_code, mark_consumed), ScheduleRepo (get_template, get_plan_items, list_by_user), ActivityRepo (list_by_user, get_by_id, create), HotkeysRepo (list_by_user, add, remove, reorder), NotificationsRepo (create_many, get_pending(planned_at <= until), mark_sent), LogsRepo (add, exists_by_idempotency_key или по notification_id), SessionsRepo (create, get_active(user_id, activity_id), list_active(user_id), close(session_id, ended_at)).

На границе репозиториев все даты/времена в UTC. Докстринги reStructuredText на русском (:param, :returns). Стиль Python: T | None, list[T], dict[K, V].
```

---

## 2. auth_linking

### 2.1 Сервис привязки (create_link_code, consume_link_code)

```
По docs/modules.md (раздел 1) реализуй модуль auth_linking для проекта control-habits. Репозитории (LinkCodesRepo, UsersRepo) уже есть.

Функции:
- create_link_code(web_session_id: str, ttl_seconds: int = 600) -> str — возвращает код (только A–Z, a–z, 0–9, _, -), сохраняет в БД с expires_at.
- consume_link_code(code: str, telegram_user_id: int) -> int | None — если код валиден, не истёк и не использован: помечает использованным, связывает с telegram_user_id, создаёт/возвращает user_id; иначе None.

Инварианты: TTL кода, один код — одно потребление. Докстринги на русском, стиль: T | None, list[T].
```

### 2.2 API и интеграция с ботом

```
По docs/requirements.md (раздел 1.1) и docs/system-design.md (поток 3.1) добавь к проекту control-habits:

1) Web API (FastAPI): эндпоинт создания кода привязки (возврат code и ссылка t.me/<bot>?start=<code>), эндпоинт проверки статуса привязки по session/коду (для polling фронтом). Используй auth_linking.create_link_code.

2) Обработчик в боте: команда /start <code> — вызов auth_linking.consume_link_code(code, telegram_user_id); ответ пользователю «Вы привязаны» или сообщение об ошибке. Если бот ещё не поднят — только хендлер /start с вызовом consume_link_code и ответом в чат.

Контекст: plan.md (онбординг), docs/ui-telegram.md (схема онбординга).
```

---

## 3. schedule_model

```
По docs/modules.md (раздел 2) и docs/domain-model.md реализуй модуль schedule_model для проекта control-habits.

Нужно:
- DTO/модели: TaskItem, EventItem (kind, title, start_time, end_time, days_of_week, activity_id?), ScheduleTemplate, DayOfWeek (enum или битмаска). PlannedItem — элемент на конкретную дату: plan_item_id, date, planned_at (UTC), type: task | event_start | event_end.
- Функция expand_template(user_id: int, date: date) -> list[PlannedItem] — по шаблону пользователя и дням недели возвращает запланированные элементы на эту дату с вычисленными UTC-временами (timezone пользователя из UsersRepo).

Зависимости: ScheduleRepo, UsersRepo. Время в UTC на выходе. Докстринги на русском.
```

---

## 4. planning_engine

```
По docs/modules.md (раздел 3) реализуй модуль planning_engine для проекта control-habits. schedule_model и репозитории уже есть.

Функция build_notification_jobs(user_id: int, date: date) -> list[NotificationJob]: использует expand_template; для каждого элемента создаёт NotificationJob с полями planned_at (UTC), type (task_prompt | event_start | event_end), plan_item_id, idempotency_key (однозначно один пуш, например plan_item_id + date + type), плюс данные для сообщения.

Опционально: сохранение в таблицу notifications с sent_at = NULL (если так задумано в дизайне). Зависимости: schedule_model, NotificationsRepo. Докстринги на русском.
```

---

## 5. bot_messages

### 5.1 Промпты для пушей (дело и событие)

```
По docs/modules.md (раздел 4) реализуй сборщики сообщений и кнопок для пушей в Telegram (проект control-habits).

Функции:
- build_task_prompt(task_planned: PlannedItem) -> (text: str, reply_markup) — текст «Сделал [title]?», кнопки: Сделал / Не сделал / Пропустить. callback_data уложить в 64 байта (короткие префиксы + id).
- build_event_start_prompt(event_planned: PlannedItem) -> (text, reply_markup) — «Начал [title]?», кнопки Начал / Не начал.
- build_event_end_prompt(event_planned: PlannedItem) -> (text, reply_markup) — «Закончил [title]?», кнопки Закончил / Пропустил.

Формат callback_data согласовать с bot_handlers (идемпотентность по notification_id или idempotency_key). Стек: aiogram 3.x. Докстринги на русском.
```

### 5.2 Клавиатура hotkeys и экран «незавершённые»

```
По docs/modules.md (раздел 4) добавь в модуль bot_messages (проект control-habits):

- build_hotkeys_keyboard(user_id: int) -> ReplyKeyboardMarkup | InlineKeyboardMarkup — список hotkey-кнопок пользователя (HotkeysRepo/ActivityRepo), подписи и callback_data или reply-клавиатура.
- build_active_sessions_message(sessions: list[ActiveSession]) -> str — текст вида «Сейчас идёт: YouTube с 14:30; Работа с 09:00».
- build_finish_buttons(sessions: list[ActiveSession]) -> InlineKeyboardMarkup — по кнопке «Закончить [название]» на каждую сессию; callback_data в пределах 64 байт (session_id или user_id+activity_id).

Зависимости: модели PlannedItem, ActiveSession; формат payload согласовать с bot_handlers. Докстринги на русском.
```

---

## 6. hotkey_sessions

```
По docs/modules.md (раздел 6) и docs/requirements.md (1.4, 1.5) реализуй модуль hotkey_sessions для проекта control-habits. SessionsRepo и ActivityRepo уже есть.

Функции:
- start_session(user_id: int, activity_id: int, now: datetime) -> int — создаёт ActiveSession, возвращает session_id. Если уже есть активная по этой активности — вернуть существующий id (идемпотентный повторный старт).
- stop_session(user_id: int, activity_id: int, now: datetime) -> float | None — выставляет ended_at = now у активной сессии, возвращает длительность в секундах; если активной нет — None (идемпотентно).
- list_active_sessions(user_id: int) -> list[ActiveSession] — все сессии с ended_at IS NULL с подгрузкой названий активностей.

Инвариант: не более одной активной сессии на (user_id, activity_id). Время в UTC. Докстринги на русском.
```

---

## 7. bot_handlers

### 7.1 Обработка callback от пушей

```
По docs/modules.md (раздел 5) и docs/requirements.md (3.3) реализуй обработку callback от пушей в боте (проект control-habits). auth_linking, hotkey_sessions, bot_messages, LogsRepo, NotificationsRepo уже есть.

Логика: при callback_query разобрать callback_data (тип + notification_id/idempotency_key). Проверить идемпотентность: есть ли уже LogEntry по этому ключу. Если да — answer_callback_query, при необходимости отредактировать сообщение («Уже учтено»). Если нет — записать LogEntry с responded_at=now(), обновить сообщение (убрать кнопки или «Учтено»), answer_callback_query. Обязательно вызывать answer_callback_query. Формат callback_data согласован с bot_messages (лимит 64 байта).
```

### 7.2 Hotkey и команда /active

```
По docs/modules.md (раздел 5) и docs/system-design.md (3.4) добавь в бота (проект control-habits):

1) Обработку нажатий hotkey-кнопок: вызов hotkey_sessions.start_session / stop_session в зависимости от текущего состояния; запись LogEntry (session_start / session_end); ответ пользователю. Идемпотентность сохранять.

2) Команду /active (или кнопку «Что сейчас идёт»): вызов list_active_sessions; сформировать сообщение через build_active_sessions_message и клавиатуру через build_finish_buttons; отправить сообщение. Callback «Закончить» по session_id — вызов stop_session, запись LogEntry, идемпотентность.

Команду /start <code> считай уже реализованной (auth_linking).
```

---

## 8. reporting

```
По docs/modules.md (раздел 7) реализуй модуль reporting для проекта control-habits.

Функция get_daily_report(user_id: int, date: date) -> DailyReport. Структура отчёта: список запланированного (planned items + типы), список фактов ответов (LogEntry с временем и статусом), список интервалов (сессии с started_at/ended_at за эту дату, длительности).

Зависимости: schedule_model.expand_template или ScheduleRepo, LogsRepo, слой для закрытых сессий за дату (SessionsRepo). Докстринги на русском. Все времена на входе/выходе в UTC или date в локальном времени пользователя — по договорённости с веб-API.
```

---

## 9. Scheduler

```
По docs/system-design.md (разделы 2.3, 3.2) и docs/modules.md (порядок п.9) реализуй планировщик отправки пушей для проекта control-habits.

Логика: периодически (например, раз в 60 секунд) или по таймеру выбирать из БД уведомления с planned_at <= now и sent_at IS NULL (get_pending). Для каждого: сформировать текст и клавиатуру через bot_messages, отправить сообщение в Telegram (Bot API), записать sent_at и при необходимости message_id (mark_sent). При ошибке Telegram — ретраи по политике; при «user blocked bot» — не ретраить, залогировать. Использовать APScheduler (или простой цикл) в том же процессе, что и приложение, или отдельно. При нескольких инстансах — выборка с FOR UPDATE SKIP LOCKED или advisory lock в Postgres.
```

---

## 10. Web API (CRUD)

```
По docs/system-design.md (2.1) и plan.md добавь в проект control-habits FastAPI-эндпоинты для MVP:

- CRUD шаблона расписания и элементов плана (TaskItem, EventItem): создание/чтение/обновление/удаление; дни недели, время в локальном времени пользователя (на входе/выходе), в БД — UTC по timezone пользователя.
- CRUD активностей и hotkey-кнопок (список, добавление, удаление, reorder).
- Эндпоинт отчёта за день: get_daily_report(user_id, date); user_id из текущей сессии (после привязки).

Авторизация: только запросы с привязанной веб-сессией (user_id). Код привязки и статус — уже есть из auth_linking. Докстринги на русском.
```

---

## 11. Web UI

```
По docs/ui-web.md и plan.md реализуй веб-интерфейс для проекта control-habits (MVP).

Страницы: вход (кнопка «Войти через Telegram», отображение кода и ссылки на бота, опционально polling статуса привязки); редактор расписания (блоки/дела, время, тип, дни недели); настройки пушей (вкл/выкл, часовой пояс, тихие часы); настройка hotkey-кнопок (список, добавление, порядок); отчёт за день (запланированное, факты ответов, длительности интервалов).

Данные через существующее Web API. После привязки — редирект/переход в настройки. Можно простой стек (HTML + JS или выбранный фреймворк). Схемы экранов — в docs/ui-web.md.
```

---

## Короткие промпты (только суть)

Если контекст уже загружен (правило Cursor, открыты docs), можно задавать короче:

| Подзадача | Короткий промпт |
|-----------|-----------------|
| 1.1 Модели + миграция | Реализуй модели SQLAlchemy и миграцию Alembic по docs/system-design.md §4 и docs/modules.md §8. |
| 1.2 Репозитории | Реализуй все репозитории из docs/modules.md §8 поверх существующих моделей. |
| 2.1 auth_linking сервис | Реализуй create_link_code и consume_link_code по docs/modules.md §1. |
| 2.2 API + бот /start | Эндпоинты создания кода и статуса привязки + хендлер /start <code> в боте по docs/system-design.md 3.1. |
| 3 schedule_model | Реализуй DTO и expand_template по docs/modules.md §2 с учётом timezone. |
| 4 planning_engine | Реализуй build_notification_jobs по docs/modules.md §3 с idempotency_key. |
| 5.1 bot_messages пуши | build_task_prompt, build_event_start_prompt, build_event_end_prompt по docs/modules.md §4, callback_data ≤ 64 байт. |
| 5.2 bot_messages hotkeys | build_hotkeys_keyboard, build_active_sessions_message, build_finish_buttons по docs/modules.md §4. |
| 6 hotkey_sessions | start_session, stop_session, list_active_sessions по docs/modules.md §6, инвариант одна активная сессия на (user, activity). |
| 7.1 bot_handlers callback | Обработка callback от пушей с идемпотентностью по docs/modules.md §5 и requirements.md 3.3. |
| 7.2 bot_handlers hotkey и /active | Обработка hotkey-кнопок и команды /active по docs/modules.md §5 и system-design 3.4. |
| 8 reporting | get_daily_report по docs/modules.md §7. |
| 9 scheduler | APScheduler: get_pending → bot_messages → Bot API → mark_sent, ретраи по docs/system-design.md 2.3, 3.2. |
| 10 Web API | CRUD расписания, активностей, hotkeys и эндпоинт отчёта по docs/system-design.md 2.1. |
| 11 Web UI | Страницы по docs/ui-web.md: вход, редактор расписания, настройки пушей/hotkeys, отчёт. |
