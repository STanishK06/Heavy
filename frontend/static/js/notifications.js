(function () {
  let notifSocket = null;
  let notifPollingTimer = null;
  let latestNotifState = { count: 0, notifications: [] };
  let refreshNotifSnapshot = async () => {};
  let syncNotifState = () => {};

  function notifSocketConnected() {
    return Boolean(notifSocket?.connected);
  }

  function ensureNotifPolling(loadNotifSnapshot) {
    if (notifPollingTimer) {
      return;
    }
    notifPollingTimer = window.setInterval(loadNotifSnapshot, 30000);
  }

  document.addEventListener('DOMContentLoaded', () => {
    const bell = document.getElementById('notifBtn');
    const dropdown = document.getElementById('notifDropdown');
    const countEl = document.getElementById('notifCount');
    const listEl = document.getElementById('notifList');

    function renderNotifs() {
      if (!listEl) {
        return;
      }
      const notifs = latestNotifState.notifications || [];
      if (!notifs.length) {
        listEl.innerHTML = '<div class="notif-empty"><i class="fa-regular fa-bell-slash" style="font-size:1.5rem;display:block;margin-bottom:8px;opacity:.4"></i>No notifications</div>';
        return;
      }
      listEl.innerHTML = notifs.map((n) => `
        <div class="notif-item ${n.is_read ? '' : 'unread'}" onclick="markRead(${n.id},this)">
          ${!n.is_read ? '<div class="notif-dot"></div>' : '<div style="width:7px;flex-shrink:0"></div>'}
          <div class="notif-body">
            <div class="notif-title">${window.HeavyLift.escHtml(n.title)}</div>
            ${n.message ? `<div class="notif-msg">${window.HeavyLift.escHtml(n.message)}</div>` : ''}
            <div class="notif-time">${n.created_at ? new Date(n.created_at).toLocaleString('en-IN') : ''}</div>
          </div>
        </div>`).join('');
    }

    function applyNotifState(state) {
      latestNotifState = {
        count: Number(state?.count || 0),
        notifications: Array.isArray(state?.notifications) ? state.notifications : [],
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
      if (!bell) {
        return;
      }
      try {
        const response = await fetch('/notifications/snapshot');
        if (!response.ok) {
          return;
        }
        applyNotifState(await response.json());
      } catch {}
    }

    function connectNotifSocket() {
      if (!bell || typeof io !== 'function') {
        ensureNotifPolling(loadNotifSnapshot);
        return;
      }
      if (notifSocket && (notifSocketConnected() || notifSocket.active)) {
        return;
      }

      notifSocket = io('/notifications', {
        path: '/socket.io',
        auth: { csrfToken: window.HeavyLift.csrfToken },
        withCredentials: true,
        reconnection: true,
        reconnectionAttempts: Infinity,
        timeout: 10000,
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
      notifSocket.on('connect_error', () => ensureNotifPolling(loadNotifSnapshot));
      notifSocket.on('disconnect', () => ensureNotifPolling(loadNotifSnapshot));
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
          notifSocket.emit('notification_refresh', { source: 'dropdown' });
        }
      }
    });

    document.addEventListener('click', () => dropdown?.classList.remove('open'));
    dropdown?.addEventListener('click', (event) => event.stopPropagation());

    loadNotifSnapshot();
    connectNotifSocket();
  });

  window.markRead = async function markRead(id, el) {
    await fetch(`/notifications/${id}/read`, { method: 'POST' });
    latestNotifState = {
      ...latestNotifState,
      count: Math.max(0, Number(latestNotifState.count || 0) - 1),
      notifications: (latestNotifState.notifications || []).map((item) => (
        item.id === id ? { ...item, is_read: true } : item
      )),
    };
    syncNotifState(latestNotifState);
    if (el) {
      el.classList.remove('unread');
      const dot = el.querySelector('.notif-dot');
      if (dot) {
        dot.style.display = 'none';
      }
    }
    if (!notifSocketConnected()) {
      await refreshNotifSnapshot();
    }
  };

  window.readAllNotifs = async function readAllNotifs() {
    await fetch('/notifications/read-all', { method: 'POST' });
    latestNotifState = {
      count: 0,
      notifications: (latestNotifState.notifications || []).map((item) => ({ ...item, is_read: true })),
    };
    syncNotifState(latestNotifState);
    if (!notifSocketConnected()) {
      await refreshNotifSnapshot();
    }
  };
})();
