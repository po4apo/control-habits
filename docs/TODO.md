# Control Habits — статус реализации

Соответствует задачам из `prompts.md`. Обновлять по мере реализации.

---

## 1. Storage

- [x] **1.1** Модели БД и миграция — SQLAlchemy 2.x, Alembic, таблицы по system-design.md
- [x] **1.2** Репозитории — UsersRepo, LinkCodesRepo, ScheduleRepo, ActivityRepo, HotkeysRepo, NotificationsRepo, LogsRepo, SessionsRepo

---

## 2. auth_linking

- [x] **2.1** Сервис привязки — create_link_code, consume_link_code (AuthLinkingService)
- [x] **2.2** API и интеграция с ботом — эндпоинты создания кода/статуса привязки, хендлер /start \<code\> в боте

---

## 3. schedule_model

- [x] **3** DTO и expand_template — TaskItem, EventItem, PlannedItem, DayOfWeek; expand_template(user_id, date) с учётом timezone

---

## 4. planning_engine

- [x] **4** build_notification_jobs — NotificationJob, idempotency_key, опционально запись в notifications

---

## 5. bot_messages

- [x] **5.1** Промпты для пушей — build_task_prompt, build_event_start_prompt, build_event_end_prompt (callback_data ≤ 64 байт)
- [x] **5.2** Клавиатура hotkeys и экран «незавершённые» — build_hotkeys_keyboard, build_active_sessions_message, build_finish_buttons

---

## 6. hotkey_sessions

- [x] **6** start_session, stop_session, list_active_sessions — инвариант одна активная сессия на (user_id, activity_id)

---

## 7. bot_handlers

- [x] **7.1** Обработка callback от пушей — идемпотентность по LogEntry, answer_callback_query
- [x] **7.2** Hotkey и команда /active — обработка hotkey-кнопок, команда /active, callback «Закончить»

---

## 8. reporting

- [x] **8** get_daily_report — planned, ответы (LogEntry), интервалы сессий за дату

---

## 9. Scheduler

- [x] **9** Планировщик пушей — get_pending → bot_messages → Bot API → mark_sent, ретраи, APScheduler

---

## 10. Web API (CRUD)

- [x] **10** FastAPI: CRUD расписания/план, активностей/hotkeys, эндпоинт отчёта; авторизация по сессии

---

## 11. Web UI

- [x] **11** Веб-интерфейс MVP — вход, редактор расписания, настройки пушей/hotkeys, отчёт за день (по ui-web.md)

---

## Сводка

| Статус   | Количество |
|----------|-------------|
| Готово   | 17          |
| Осталось | 0           |

**Готово:** 1.1, 1.2, 2.1, 2.2, 3, 4, 5.1, 5.2, 6, 7.1, 7.2, 8, 9, 10, 11  
**Все задачи из prompts.md реализованы.**
