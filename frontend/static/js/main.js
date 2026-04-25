/**
 * HeavyLift CRM - main.js
 * Sidebar, clock, notifications, Socket.IO, modals, form helpers
 */
const csrfMeta = document.querySelector('meta[name="csrf-token"]');
window.csrfToken = csrfMeta?.getAttribute('content') || '';

const originalFetch = window.fetch.bind(window);
window.fetch = (input, init = {}) => {
  const method = (init.method || input?.method || 'GET').toUpperCase();
  const requestUrl = typeof input === 'string' ? input : input?.url || window.location.href;
  const url = new URL(requestUrl, window.location.origin);
  if (url.origin !== window.location.origin || ['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
    return originalFetch(input, init);
  }

  const headers = new Headers(init.headers || input?.headers || {});
  if (window.csrfToken && !headers.has('X-CSRF-Token')) {
    headers.set('X-CSRF-Token', window.csrfToken);
  }
  return originalFetch(input, {...init, headers});
};

let notifSocket = null;
let notifPollingTimer = null;
let latestNotifState = {count: 0, notifications: []};
let refreshNotifSnapshot = async () => {};
let syncNotifState = () => {};

function notifSocketConnected() {
  return Boolean(notifSocket?.connected);
}

document.addEventListener('DOMContentLoaded', () => {
  const sidebar = document.getElementById('sidebar');
  const overlay = document.getElementById('sidebarOverlay');
  const mobBtn = document.getElementById('mobileToggle');

  const openSb = () => {
    sidebar?.classList.add('open');
    overlay?.classList.add('show');
  };
  const closeSb = () => {
    sidebar?.classList.remove('open');
    overlay?.classList.remove('show');
  };

  mobBtn?.addEventListener('click', () => sidebar?.classList.contains('open') ? closeSb() : openSb());
  overlay?.addEventListener('click', closeSb);

  const clockEl = document.getElementById('liveClock');
  const tick = () => {
    if (!clockEl) return;
    clockEl.textContent = new Date().toLocaleString('en-IN', {
      year: 'numeric',
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  };
  tick();
  setInterval(tick, 30000);

  document.querySelectorAll('.alert').forEach((alertEl) => {
    setTimeout(() => {
      alertEl.style.transition = 'opacity .5s';
      alertEl.style.opacity = '0';
      setTimeout(() => alertEl.remove(), 500);
    }, 5000);
  });

  const bell = document.getElementById('notifBtn');
  const dropdown = document.getElementById('notifDropdown');
  const countEl = document.getElementById('notifCount');
  const listEl = document.getElementById('notifList');

  function renderNotifs() {
    if (!listEl) return;
    const notifs = latestNotifState.notifications || [];
    if (!notifs.length) {
      listEl.innerHTML = '<div class="notif-empty"><i class="fa-regular fa-bell-slash" style="font-size:1.5rem;display:block;margin-bottom:8px;opacity:.4"></i>No notifications</div>';
      return;
    }
    listEl.innerHTML = notifs.map((n) => `
      <div class="notif-item ${n.is_read ? '' : 'unread'}" onclick="markRead(${n.id},this)">
        ${!n.is_read ? '<div class="notif-dot"></div>' : '<div style="width:7px;flex-shrink:0"></div>'}
        <div class="notif-body">
          <div class="notif-title">${escHtml(n.title)}</div>
          ${n.message ? `<div class="notif-msg">${escHtml(n.message)}</div>` : ''}
          <div class="notif-time">${n.created_at ? new Date(n.created_at).toLocaleString('en-IN') : ''}</div>
        </div>
      </div>`).join('');
  }

  function applyNotifState(state) {
    latestNotifState = {
      count: Number(state?.count || 0),
      notifications: Array.isArray(state?.notifications) ? state.notifications : []
    };

    if (countEl) {
      if (latestNotifState.count > 0) {
        countEl.textContent = latestNotifState.count > 99 ? '99+' : latestNotifState.count;
        countEl.classList.add('visible');
      } else {
        countEl.classList.remove('visible');
        countEl.textContent = '';
      }
    }

    if (dropdown?.classList.contains('open')) {
      renderNotifs();
    }
  }

  async function loadNotifSnapshot() {
    if (!bell) return;
    try {
      const response = await fetch('/notifications/snapshot');
      if (!response.ok) return;
      applyNotifState(await response.json());
    } catch {}
  }

  function ensureNotifPolling() {
    if (notifPollingTimer) return;
    notifPollingTimer = window.setInterval(() => {
      loadNotifSnapshot();
    }, 30000);
  }

  function connectNotifSocket() {
    if (!bell || typeof io !== 'function') {
      ensureNotifPolling();
      return;
    }
    if (notifSocket && (notifSocketConnected() || notifSocket.active)) {
      return;
    }

    notifSocket = io('/notifications', {
      path: '/socket.io',
      auth: {csrfToken: window.csrfToken},
      withCredentials: true,
      reconnection: true,
      reconnectionAttempts: Infinity,
      timeout: 10000
    });

    notifSocket.on('connect', () => {
      if (notifPollingTimer) {
        window.clearInterval(notifPollingTimer);
        notifPollingTimer = null;
      }
    });

    notifSocket.on('notification_test', () => {});

    notifSocket.on('notification_snapshot', (payload) => {
      if (payload?.type === 'snapshot') {
        applyNotifState(payload);
      }
    });

    notifSocket.on('connect_error', () => {
      ensureNotifPolling();
    });

    notifSocket.on('disconnect', () => {
      ensureNotifPolling();
    });
  }

  syncNotifState = applyNotifState;
  refreshNotifSnapshot = loadNotifSnapshot;

  bell?.addEventListener('click', (event) => {
    event.stopPropagation();
    const open = dropdown?.classList.contains('open');
    dropdown?.classList.toggle('open', !open);
    if (!open) {
      renderNotifs();
      if (notifSocketConnected()) {
        notifSocket.emit('notification_refresh', {source: 'dropdown'});
      }
    }
  });
  document.addEventListener('click', () => dropdown?.classList.remove('open'));
  dropdown?.addEventListener('click', (event) => event.stopPropagation());

  loadNotifSnapshot();
  connectNotifSocket();

  document.querySelectorAll('.filter-toggle').forEach((btn) => {
    btn.addEventListener('click', () => {
      const body = btn.nextElementSibling;
      const icon = btn.querySelector('.filter-chevron');
      body?.classList.toggle('open');
      if (icon) icon.style.transform = body?.classList.contains('open') ? 'rotate(180deg)' : '';
    });
  });

  const inqDate = document.getElementById('inquiry_date');
  const fuDate = document.getElementById('followup_date');
  if (inqDate && fuDate) {
    inqDate.addEventListener('change', () => {
      if (!fuDate.value || fuDate.dataset.autoset === 'true') {
        const nextDate = new Date(inqDate.value);
        nextDate.setDate(nextDate.getDate() + 10);
        fuDate.value = nextDate.toISOString().split('T')[0];
        fuDate.dataset.autoset = 'true';
      }
    });
    fuDate.addEventListener('change', () => {
      fuDate.dataset.autoset = 'false';
    });
  }

  document.querySelectorAll('[data-add-ref]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = document.getElementById(btn.dataset.addRef);
      if (target) {
        target.style.display = 'grid';
        btn.style.display = 'none';
      }
    });
  });

  document.querySelectorAll('th.sortable').forEach((th) => {
    th.addEventListener('click', () => {
      const url = new URL(window.location.href);
      const cur = url.searchParams.get('sort');
      const dir = url.searchParams.get('dir');
      url.searchParams.set('sort', th.dataset.col);
      url.searchParams.set('dir', cur === th.dataset.col && dir === 'asc' ? 'desc' : 'asc');
      window.location = url.toString();
    });
  });

  document.querySelectorAll('.clickable-row').forEach((row) => {
    row.addEventListener('click', () => {
      const parent = row.parentElement;
      const lastDragAt = Number(parent?.dataset.lastDragAt || 0);
      if (lastDragAt && Date.now() - lastDragAt < 300) {
        return;
      }
      if (row.dataset.href) window.location.href = row.dataset.href;
    });
  });

  const courseSelect = document.getElementById('course_id');
  const offerSelect = document.getElementById('offer_id');
  const feesTotalEl = document.getElementById('fees_total');

  async function recalcFees() {
    if (!courseSelect || !feesTotalEl) return;
    const cid = courseSelect.value;
    const oid = offerSelect?.value || null;
    if (!cid) {
      feesTotalEl.value = '';
      return;
    }
    try {
      const response = await fetch('/offers/api/calculate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({course_id: cid, offer_id: oid})
      });
      const data = await response.json();
      feesTotalEl.value = data.fees;
    } catch {}
  }

  courseSelect?.addEventListener('change', recalcFees);
  offerSelect?.addEventListener('change', recalcFees);
});

function escHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

async function markRead(id, el) {
  await fetch(`/notifications/${id}/read`, {method: 'POST'});
  latestNotifState = {
    ...latestNotifState,
    count: Math.max(0, Number(latestNotifState.count || 0) - 1),
    notifications: (latestNotifState.notifications || []).map((item) => (
      item.id === id ? {...item, is_read: true} : item
    ))
  };
  syncNotifState(latestNotifState);
  if (el) {
    el.classList.remove('unread');
    const dot = el.querySelector('.notif-dot');
    if (dot) dot.style.display = 'none';
  }
  if (!notifSocketConnected()) {
    await refreshNotifSnapshot();
  }
}

async function readAllNotifs() {
  await fetch('/notifications/read-all', {method: 'POST'});
  latestNotifState = {
    count: 0,
    notifications: (latestNotifState.notifications || []).map((item) => ({...item, is_read: true}))
  };
  syncNotifState(latestNotifState);
  if (!notifSocketConnected()) {
    await refreshNotifSnapshot();
  }
}

  async function openWaModal(inqId, name, mobile) {
  const modal = document.getElementById('waModal');
  if (!modal) return;
  modal.querySelector('#wa_inq_id').value = inqId;
  modal.querySelector('#wa_name').textContent = name;
  modal.querySelector('#wa_mobile').textContent = mobile;
  const sel = modal.querySelector('#wa_template');
  const msgEl = modal.querySelector('#wa_message');
  try {
    const response = await fetch('/whatsapp/api/templates');
    const data = await response.json();
    if (!response.ok || !data.ok) {
      sel.innerHTML = '<option value="">- Templates unavailable -</option>';
      msgEl.value = '';
      modal.classList.add('open');
      return;
    }
    const tmpls = Array.isArray(data.templates) ? data.templates : [];
    sel.innerHTML = '<option value="">- Select template -</option>' +
      tmpls.map((t) => `<option value="${t.id}" data-msg="${encodeURIComponent(t.description || '')}">${escHtml(t.name)}</option>`).join('');
    sel.onchange = () => {
      const opt = sel.selectedOptions[0];
      if (!opt || !opt.dataset.msg) {
        msgEl.value = '';
        return;
      }
      let msg = decodeURIComponent(opt.dataset.msg);
      msg = msg.replace(/\[NAME\]/g, name).replace(/\[MOBILE\]/g, mobile);
      msgEl.value = msg;
    };
  } catch {}
  modal.classList.add('open');
}

function closeWaModal() {
  document.getElementById('waModal')?.classList.remove('open');
}

document.getElementById('waSendBtn')?.addEventListener('click', async () => {
  const modal = document.getElementById('waModal');
  const inqId = modal.querySelector('#wa_inq_id').value;
  const msg = modal.querySelector('#wa_message').value.trim();
  const popup = window.open('', '_blank', 'noopener');
  try {
    const response = await fetch(`/inquiries/${inqId}/whatsapp-send`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg})
    });
    const data = await response.json();
    if (data.ok) {
      if (popup) {
        popup.location = data.url;
      } else {
        window.location.href = data.url;
      }
      closeWaModal();
    } else {
      popup?.close();
      alert(data.msg || 'Error sending.');
    }
  } catch {
    popup?.close();
    alert('Error connecting.');
  }
});

function openPwModal(uid, username) {
  const modal = document.getElementById('pwModal');
  if (!modal) return;
  modal.querySelector('#pw_uid').value = uid;
  modal.querySelector('#pw_username').textContent = username;
  modal.querySelector('#pw_new').value = '';
  modal.querySelector('#pw_confirm').value = '';
  modal.classList.add('open');
}

function closePwModal() {
  document.getElementById('pwModal')?.classList.remove('open');
}

document.getElementById('pwSaveBtn')?.addEventListener('click', async () => {
  const modal = document.getElementById('pwModal');
  const uid = modal.querySelector('#pw_uid').value;
  const newPw = modal.querySelector('#pw_new').value;
  const conf = modal.querySelector('#pw_confirm').value;
  if (newPw !== conf) {
    alert('Passwords do not match.');
    return;
  }
  if (newPw.length < 8) {
    alert('Minimum 8 characters required.');
    return;
  }
  try {
    const response = await fetch(`/users/${uid}/change-password`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({new_password: newPw})
    });
    const data = await response.json();
    if (data.ok) {
      closePwModal();
      alert('Password updated.');
    } else {
      alert(data.msg);
    }
  } catch {
    alert('Error connecting to server.');
  }
});

document.querySelectorAll('.modal-overlay').forEach((modal) => {
  modal.addEventListener('click', (event) => {
    if (event.target === modal) modal.classList.remove('open');
  });
});
