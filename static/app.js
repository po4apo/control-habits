/**
 * Control Habits — SPA (MVP).
 * Маршруты: #/ (вход), #/schedule, #/notifications, #/hotkeys, #/report.
 */

const API_BASE = '/api';
const SESSION_KEY = 'web_session_id';

function getSessionId() {
  return localStorage.getItem(SESSION_KEY);
}

function setSessionId(id) {
  if (id) localStorage.setItem(SESSION_KEY, id);
  else localStorage.removeItem(SESSION_KEY);
}

async function api(path, options = {}) {
  const sid = getSessionId();
  const headers = {
    'Content-Type': 'application/json',
    ...(sid && { 'X-Web-Session-Id': sid }),
    ...options.headers,
  };
  const res = await fetch(API_BASE + path, { ...options, headers });
  if (res.status === 401) {
    setSessionId(null);
    window.location.hash = '/';
    throw new Error('Сессия истекла');
  }
  if (!res.ok) {
    const t = await res.text();
    let msg = t;
    try {
      const j = JSON.parse(t);
      if (j.detail) msg = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail);
    } catch (_) {}
    throw new Error(msg);
  }
  if (res.status === 204) return null;
  return res.json();
}

// ——— Роутер ———
const routes = {
  '/': 'login',
  '/schedule': 'schedule',
  '/notifications': 'notifications',
  '/hotkeys': 'hotkeys',
  '/report': 'report',
};

function getRoute() {
  const hash = window.location.hash.slice(1) || '/';
  const path = hash.split('?')[0];
  return routes[path] || (getSessionId() ? 'schedule' : 'login');
}

function renderNav() {
  const nav = document.getElementById('mainNav');
  if (!nav) return;
  const sid = getSessionId();
  if (!sid) {
    nav.innerHTML = '';
    return;
  }
  const current = window.location.hash.slice(1) || '/';
  nav.innerHTML =
    [
      { path: '/schedule', label: 'Расписание' },
      { path: '/hotkeys', label: 'Кнопки' },
      { path: '/notifications', label: 'Уведомления' },
      { path: '/report', label: 'Отчёт' },
    ]
      .map(
        (r) =>
          `<a href="#${r.path}" class="${current === r.path ? 'active' : ''}">${r.label}</a>`
      )
      .join('') +
    '<a href="#" class="nav-logout" id="btnLogout">Выйти</a>';

  const btnLogout = document.getElementById('btnLogout');
  if (btnLogout) {
    btnLogout.addEventListener('click', (e) => {
      e.preventDefault();
      setSessionId(null);
      window.location.hash = '/';
      render('login');
    });
  }
}

function render(page) {
  const main = document.getElementById('mainContent');
  if (!main) return;
  main.innerHTML = '';
  renderNav();
  if (page === 'login') return renderLogin(main);
  if (page === 'schedule') return renderSchedule(main);
  if (page === 'notifications') return renderNotifications(main);
  if (page === 'hotkeys') return renderHotkeys(main);
  if (page === 'report') return renderReport(main);
}

// ——— Страница входа ———
function renderLogin(container) {
  container.innerHTML = `
    <div class="login-box">
      <h1>Control Habits</h1>
      <p class="text-muted">Войдите через Telegram, чтобы настроить расписание и кнопки.</p>
      <button type="button" class="btn mt-2" id="btnLogin">Войти через Telegram</button>
      <div id="linkCodeBlock" class="hidden">
        <div class="link-code-block">
          <p>Открой бота и введи код привязки:</p>
          <div class="code-value" id="codeValue"></div>
          <button type="button" class="btn btn-secondary" id="btnCopy">Копировать</button>
          <p class="mt-1">Ссылка: <a href="#" id="botLink" class="link-bot" target="_blank" rel="noopener">Открыть бота</a></p>
          <p class="code-expiry">Код действителен 10 минут. После привязки вы перейдёте в настройки.</p>
        </div>
      </div>
      <p id="loginError" class="error-msg hidden"></p>
    </div>
  `;

  const btnLogin = document.getElementById('btnLogin');
  const linkCodeBlock = document.getElementById('linkCodeBlock');
  const codeValue = document.getElementById('codeValue');
  const btnCopy = document.getElementById('btnCopy');
  const botLink = document.getElementById('botLink');
  const loginError = document.getElementById('loginError');

  btnLogin.addEventListener('click', async () => {
    loginError.classList.add('hidden');
    try {
      const body = await api('/auth/link-code', { method: 'POST', body: '{}' });
      // Не перезаписывать сессию в localStorage до подтверждения в боте:
      // иначе старая рабочая сессия теряется и все запросы получают 401.
      codeValue.textContent = body.code;
      botLink.href = body.link;
      linkCodeBlock.classList.remove('hidden');
      startLinkPolling(body.web_session_id);
    } catch (e) {
      loginError.textContent = e.message || 'Ошибка создания кода';
      loginError.classList.remove('hidden');
    }
  });

  btnCopy.addEventListener('click', () => {
    navigator.clipboard.writeText(codeValue.textContent);
  });

  function startLinkPolling(webSessionId) {
    const t = setInterval(async () => {
      try {
        const r = await fetch(
          `${API_BASE}/auth/link-status?web_session_id=${encodeURIComponent(webSessionId)}`
        );
        const data = await r.json();
        if (data.status === 'consumed') {
          clearInterval(t);
          setSessionId(webSessionId); // сохраняем сессию только после подтверждения в боте
          window.location.hash = '/notifications';
          window.location.reload();
        }
      } catch (_) {}
    }, 2000);
  }
}

// ——— Редактор расписания ———
const DAYS_LABELS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

function renderSchedule(container) {
  container.innerHTML = `
    <h1 class="page-title">Расписание дня</h1>
    <div class="card">
      <div class="card-header">
        <span>Часовой пояс: <span id="scheduleTz">—</span></span>
        <button type="button" class="btn" id="btnAddItem">+ Добавить</button>
      </div>
      <ul class="schedule-list" id="scheduleList"></ul>
    </div>
    <p id="scheduleError" class="error-msg hidden"></p>
  `;

  const list = document.getElementById('scheduleList');
  const btnAdd = document.getElementById('btnAddItem');
  const scheduleTz = document.getElementById('scheduleTz');
  const scheduleError = document.getElementById('scheduleError');

  let templateId = null;
  let items = [];

  async function load() {
    try {
      const [template, settings] = await Promise.all([
        api('/schedule/template'),
        api('/users/me'),
      ]);
      scheduleTz.textContent = settings.timezone;
      if (!template) {
        const created = await api('/schedule/template', {
          method: 'POST',
          body: JSON.stringify({ name: 'Основное' }),
        });
        templateId = created.id;
        items = [];
      } else {
        templateId = template.id;
        items = await api(`/schedule/template/${template.id}/items`);
      }
      renderList();
    } catch (e) {
      scheduleError.textContent = e.message;
      scheduleError.classList.remove('hidden');
    }
  }

  function renderList() {
    list.innerHTML = items
      .map((it) => {
        const timeStr =
          it.kind === 'event'
            ? `${it.start_time} – ${it.end_time}`
            : it.start_time;
        return `
          <li class="schedule-item" data-id="${it.id}">
            <span class="schedule-time">${timeStr}</span>
            <span class="schedule-title">${escapeHtml(it.title)}</span>
            <span class="schedule-kind">${it.kind === 'event' ? 'Событие' : 'Дело'}</span>
            <div class="schedule-actions">
              <button type="button" class="btn btn-secondary" data-edit="${it.id}">Изменить</button>
              <button type="button" class="btn btn-danger" data-delete="${it.id}">Удалить</button>
            </div>
          </li>
        `;
      })
      .join('');

    list.querySelectorAll('[data-edit]').forEach((el) => {
      el.addEventListener('click', () => openItemForm(Number(el.dataset.edit)));
    });
    list.querySelectorAll('[data-delete]').forEach((el) => {
      el.addEventListener('click', () => deleteItem(Number(el.dataset.delete)));
    });
  }

  function openItemForm(editId = null) {
    const item = editId ? items.find((i) => i.id === editId) : null;
    const isEvent = item ? item.kind === 'event' : false;
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <h2>${item ? 'Редактировать' : 'Добавить'} элемент</h2>
        <div class="form-group">
          <label>Тип</label>
          <select id="formKind">
            <option value="task" ${!isEvent ? 'selected' : ''}>Дело</option>
            <option value="event" ${isEvent ? 'selected' : ''}>Событие</option>
          </select>
        </div>
        <div class="form-group">
          <label>Название</label>
          <input type="text" id="formTitle" value="${item ? escapeHtml(item.title) : ''}" placeholder="Название">
        </div>
        <div class="form-group">
          <label>Время начала</label>
          <input type="time" id="formStart" value="${item ? item.start_time : '09:00'}">
        </div>
        <div class="form-group" id="formEndGroup">
          <label>Время конца</label>
          <input type="time" id="formEnd" value="${item ? item.end_time : '09:00'}">
        </div>
        <div class="form-group">
          <label>Дни недели</label>
          <div class="days-row" id="formDays"></div>
        </div>
        <div class="modal-actions">
          <button type="button" class="btn" id="modalSave">Сохранить</button>
          <button type="button" class="btn btn-secondary" id="modalCancel">Отмена</button>
        </div>
      </div>
    `;

    const daysRow = modal.querySelector('#formDays');
    const defaultDays = item ? item.days_of_week : [1, 2, 3, 4, 5];
    for (let d = 1; d <= 7; d++) {
      const chip = document.createElement('span');
      chip.className = 'day-chip' + (defaultDays.includes(d) ? ' selected' : '');
      chip.innerHTML = `<label><input type="checkbox" data-day="${d}" ${defaultDays.includes(d) ? 'checked' : ''}>${DAYS_LABELS[d - 1]}</label>`;
      chip.querySelector('input').addEventListener('change', (e) => {
        chip.classList.toggle('selected', e.target.checked);
      });
      daysRow.appendChild(chip);
    }

    const kindSelect = modal.querySelector('#formKind');
    const endGroup = modal.querySelector('#formEndGroup');
    kindSelect.addEventListener('change', () => {
      endGroup.classList.toggle('hidden', kindSelect.value !== 'event');
    });
    endGroup.classList.toggle('hidden', !isEvent);

    modal.querySelector('#modalCancel').addEventListener('click', () => modal.remove());
    modal.querySelector('#modalSave').addEventListener('click', async () => {
      const title = modal.querySelector('#formTitle').value.trim();
      const start = modal.querySelector('#formStart').value;
      const end = modal.querySelector('#formEnd').value;
      const days = [...modal.querySelectorAll('#formDays input:checked')].map(
        (c) => Number(c.dataset.day)
      );
      if (!title || days.length === 0) return;
      try {
        if (item) {
          await api(`/schedule/plan-items/${item.id}`, {
            method: 'PATCH',
            body: JSON.stringify({
              kind: kindSelect.value,
              title,
              start_time: start,
              end_time: end,
              days_of_week: days,
            }),
          });
        } else {
          await api(`/schedule/template/${templateId}/items`, {
            method: 'POST',
            body: JSON.stringify({
              kind: kindSelect.value,
              title,
              start_time: start,
              end_time: end,
              days_of_week: days,
            }),
          });
        }
        modal.remove();
        load();
      } catch (e) {
        alert(e.message);
      }
    });
    document.body.appendChild(modal);
  }

  async function deleteItem(id) {
    if (!confirm('Удалить элемент?')) return;
    try {
      await api(`/schedule/plan-items/${id}`, { method: 'DELETE' });
      load();
    } catch (e) {
      scheduleError.textContent = e.message;
      scheduleError.classList.remove('hidden');
    }
  }

  btnAdd.addEventListener('click', () => openItemForm(null));
  load();
}

// ——— Настройки пушей ———
function renderNotifications(container) {
  container.innerHTML = `
    <h1 class="page-title">Уведомления в Telegram</h1>
    <div class="card">
      <div class="form-group">
        <label>Пуши по расписанию</label>
        <select id="pushEnabled">
          <option value="true">Вкл</option>
          <option value="false">Выкл</option>
        </select>
      </div>
      <div class="form-group">
        <label>Часовой пояс</label>
        <select id="timezone"></select>
      </div>
      <div class="form-group">
        <label>Тихие часы (не слать)</label>
        <div style="display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap;">
          с <input type="time" id="quietFrom" value="22:00"> до <input type="time" id="quietTo" value="07:00">
        </div>
      </div>
      <button type="button" class="btn mt-2" id="btnSaveNotif">Сохранить</button>
    </div>
    <p id="notifError" class="error-msg hidden"></p>
  `;

  const timezoneSelect = document.getElementById('timezone');
  const pushEnabled = document.getElementById('pushEnabled');
  const quietFrom = document.getElementById('quietFrom');
  const quietTo = document.getElementById('quietTo');
  const btnSave = document.getElementById('btnSaveNotif');
  const notifError = document.getElementById('notifError');

  const commonTimezones = [
    'Europe/Moscow',
    'Europe/Samara',
    'Asia/Yekaterinburg',
    'Asia/Novosibirsk',
    'Europe/Kaliningrad',
    'UTC',
  ];

  commonTimezones.forEach((tz) => {
    const opt = document.createElement('option');
    opt.value = tz;
    opt.textContent = tz;
    timezoneSelect.appendChild(opt);
  });

  async function load() {
    try {
      const settings = await api('/users/me');
      timezoneSelect.value = settings.timezone;
      if (!commonTimezones.includes(settings.timezone)) {
        const opt = document.createElement('option');
        opt.value = settings.timezone;
        opt.textContent = settings.timezone;
        timezoneSelect.insertBefore(opt, timezoneSelect.firstChild);
        timezoneSelect.value = settings.timezone;
      }
    } catch (e) {
      notifError.textContent = e.message;
      notifError.classList.remove('hidden');
    }
  }

  btnSave.addEventListener('click', async () => {
    notifError.classList.add('hidden');
    try {
      await api('/users/me', {
        method: 'PATCH',
        body: JSON.stringify({ timezone: timezoneSelect.value }),
      });
      notifError.textContent = '';
      notifError.classList.add('hidden');
      alert('Часовой пояс сохранён. Настройки «Пуши вкл» и «Тихие часы» будут доступны в следующей версии.');
    } catch (e) {
      notifError.textContent = e.message;
      notifError.classList.remove('hidden');
    }
  });

  load();
}

// ——— Hotkey-кнопки ———
function renderHotkeys(container) {
  container.innerHTML = `
    <h1 class="page-title">Быстрые кнопки в боте</h1>
    <div class="card">
      <div class="card-header">
        <span></span>
        <button type="button" class="btn" id="btnAddHotkey">+ Добавить</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr><th>Название</th><th>Действия</th></tr>
          </thead>
          <tbody id="hotkeysBody"></tbody>
        </table>
      </div>
    </div>
    <p id="hotkeysError" class="error-msg hidden"></p>
  `;

  const tbody = document.getElementById('hotkeysBody');
  const btnAdd = document.getElementById('btnAddHotkey');
  const hotkeysError = document.getElementById('hotkeysError');

  let hotkeys = [];

  async function load() {
    try {
      hotkeys = await api('/activities/hotkeys');
      tbody.innerHTML = hotkeys
        .map(
          (h) => `
          <tr>
            <td>${escapeHtml(h.name || h.label)}</td>
            <td class="table-actions">
              <button type="button" class="btn btn-secondary" data-up="${h.id}" title="Выше">↑</button>
              <button type="button" class="btn btn-secondary" data-down="${h.id}" title="Ниже">↓</button>
              <button type="button" class="btn btn-danger" data-delete="${h.id}">Удалить</button>
            </td>
          </tr>
        `
        )
        .join('');

        tbody.querySelectorAll('[data-delete]').forEach((el) => {
          el.addEventListener('click', () => deleteHotkey(Number(el.dataset.delete)));
        });
        tbody.querySelectorAll('[data-up]').forEach((el) => {
          el.addEventListener('click', () => moveHotkey(Number(el.dataset.up), -1));
        });
        tbody.querySelectorAll('[data-down]').forEach((el) => {
          el.addEventListener('click', () => moveHotkey(Number(el.dataset.down), 1));
        });
    } catch (e) {
      hotkeysError.textContent = e.message;
      hotkeysError.classList.remove('hidden');
    }
  }

  async function deleteHotkey(id) {
    if (!confirm('Удалить кнопку?')) return;
    try {
      await api(`/activities/hotkeys/${id}`, { method: 'DELETE' });
      load();
    } catch (e) {
      hotkeysError.textContent = e.message;
      hotkeysError.classList.remove('hidden');
    }
  }

  async function moveHotkey(id, delta) {
    const idx = hotkeys.findIndex((h) => h.id === id);
    if (idx === -1) return;
    const newIdx = Math.max(0, Math.min(hotkeys.length - 1, idx + delta));
    if (newIdx === idx) return;
    const reordered = [...hotkeys];
    const [removed] = reordered.splice(idx, 1);
    reordered.splice(newIdx, 0, removed);
    try {
      await api('/activities/hotkeys/reorder', {
        method: 'PUT',
        body: JSON.stringify({ hotkey_ids: reordered.map((h) => h.id) }),
      });
      load();
    } catch (e) {
      hotkeysError.textContent = e.message;
      hotkeysError.classList.remove('hidden');
    }
  }

  btnAdd.addEventListener('click', () => {
    const modal = document.createElement('div');
    modal.className = 'modal-overlay';
    modal.innerHTML = `
      <div class="modal">
        <h2>Добавить кнопку</h2>
        <div class="form-group">
          <label>Название</label>
          <input type="text" id="addName" placeholder="Например: YouTube, Работа, Чтение">
        </div>
        <div class="modal-actions">
          <button type="button" class="btn" id="addSave">Добавить</button>
          <button type="button" class="btn btn-secondary" id="addCancel">Отмена</button>
        </div>
      </div>
    `;
    modal.querySelector('#addCancel').addEventListener('click', () => modal.remove());
    modal.querySelector('#addSave').addEventListener('click', async () => {
      const name = modal.querySelector('#addName').value.trim();
      if (!name) return;
      try {
        await api('/activities/hotkeys', {
          method: 'POST',
          body: JSON.stringify({ name }),
        });
        modal.remove();
        load();
      } catch (e) {
        alert(e.message);
      }
    });
    document.body.appendChild(modal);
  });

  load();
}

// ——— Отчёт за день ———
function formatDuration(sec) {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  if (h > 0) return `${h} ч ${m} мин`;
  return `${m} мин`;
}

function formatTime(dtStr) {
  const d = new Date(dtStr);
  return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
}

function renderReport(container) {
  const today = new Date().toISOString().slice(0, 10);
  container.innerHTML = `
    <h1 class="page-title">Отчёт за день</h1>
    <div class="report-date-bar">
      <input type="date" id="reportDate" value="${today}">
      <button type="button" class="btn btn-secondary" id="reportPrev">←</button>
      <button type="button" class="btn btn-secondary" id="reportNext">→</button>
    </div>
    <div id="reportContent"></div>
    <p id="reportError" class="error-msg hidden"></p>
  `;

  const dateInput = document.getElementById('reportDate');
  const reportContent = document.getElementById('reportContent');
  const reportError = document.getElementById('reportError');

  async function load() {
    const date = dateInput.value;
    reportError.classList.add('hidden');
    try {
      const data = await api(`/report/daily?date=${date}`);
      const planned = data.planned || [];
      const answers = data.answers || [];
      const intervals = data.intervals || [];

          const byPlanItem = new Map();
          planned.forEach((p) => {
            if (!byPlanItem.has(p.plan_item_id)) {
              byPlanItem.set(p.plan_item_id, { items: [], title: p.title, start_time: p.start_time, end_time: p.end_time });
            }
            const rec = byPlanItem.get(p.plan_item_id);
            rec.items.push(p);
          });

          const answerByKey = new Map();
          answers.forEach((a) => {
            const key = a.plan_item_id ? `p${a.plan_item_id}` : `a${a.activity_id}`;
            if (!answerByKey.has(key)) answerByKey.set(key, []);
            answerByKey.get(key).push(a);
          });

          const rows = [];
          byPlanItem.forEach((rec, planItemId) => {
            rec.items.sort((a, b) => new Date(a.planned_at) - new Date(b.planned_at));
            const first = rec.items[0];
            const timeLabel =
              first.type === 'event_start' || first.type === 'event_end'
                ? `${rec.start_time}–${rec.end_time}`
                : rec.start_time;
            const plannedText = `${timeLabel} ${rec.title}`;
            const ans = answerByKey.get(`p${planItemId}`) || [];
            const factParts = ans.map((a) => {
              if (a.action.includes('done') || a.action === 'task_done') return `Сделал (${formatTime(a.responded_at)})`;
              if (a.action.includes('not_done') || a.action === 'task_not_done') return 'Не сделал (—)';
              if (a.action.includes('started') || a.action === 'event_started') return `Начал ${formatTime(a.responded_at)}`;
              if (a.action.includes('ended') || a.action === 'event_ended') return `Закончил ${formatTime(a.responded_at)}`;
              if (a.action.includes('skipped')) return 'Пропустил';
              return a.action;
            });
            rows.push({ planned: plannedText, fact: factParts.join(', ') || '—' });
          });

          reportContent.innerHTML = `
        <div class="report-section">
          <h3>Запланировано / Факт</h3>
          ${rows.length ? rows.map((r) => `<div class="report-row"><div class="report-planned">${escapeHtml(r.planned)}</div><div class="report-fact">${escapeHtml(r.fact)}</div></div>`).join('') : '<p class="text-muted">Нет запланированного на эту дату.</p>'}
        </div>
        <div class="report-section">
          <h3>Интервалы (hotkey)</h3>
          <ul class="report-intervals">
            ${intervals.length ? intervals.map((i) => `<li>${escapeHtml(i.activity_name)} ${formatTime(i.started_at)} – ${formatTime(i.ended_at)} (${formatDuration(i.duration_seconds)})</li>`).join('') : '<li class="text-muted">Нет интервалов за этот день.</li>'}
          </ul>
        </div>
      `;
    } catch (e) {
      reportError.textContent = e.message;
      reportError.classList.remove('hidden');
    }
  }

  dateInput.addEventListener('change', load);
  document.getElementById('reportPrev').addEventListener('click', () => {
    const d = new Date(dateInput.value);
    d.setDate(d.getDate() - 1);
    dateInput.value = d.toISOString().slice(0, 10);
    load();
  });
  document.getElementById('reportNext').addEventListener('click', () => {
    const d = new Date(dateInput.value);
    d.setDate(d.getDate() + 1);
    dateInput.value = d.toISOString().slice(0, 10);
    load();
  });
  load();
}

function escapeHtml(s) {
  if (s == null) return '';
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

// ——— Инициализация ———
function init() {
  const page = getRoute();
  if (page !== 'login' && !getSessionId()) {
    window.location.hash = '/';
    render('login');
    return;
  }
  render(page);
}

window.addEventListener('hashchange', init);
window.addEventListener('load', init);
