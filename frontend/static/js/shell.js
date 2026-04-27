(function () {
  function initSidebar() {
    const sidebar = document.getElementById('sidebar');
    const overlay = document.getElementById('sidebarOverlay');
    const mobileToggle = document.getElementById('mobileToggle');

    const openSidebar = () => {
      sidebar?.classList.add('open');
      overlay?.classList.add('show');
    };
    const closeSidebar = () => {
      sidebar?.classList.remove('open');
      overlay?.classList.remove('show');
    };

    mobileToggle?.addEventListener('click', () => (
      sidebar?.classList.contains('open') ? closeSidebar() : openSidebar()
    ));
    overlay?.addEventListener('click', closeSidebar);
  }

  function initClock() {
    const clockEl = document.getElementById('liveClock');
    const tick = () => {
      if (!clockEl) {
        return;
      }
      clockEl.textContent = new Date().toLocaleString('en-IN', {
        year: 'numeric',
        month: 'short',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    };
    tick();
    window.setInterval(tick, 30000);
  }

  function initAlerts() {
    document.querySelectorAll('.alert').forEach((alertEl) => {
      window.setTimeout(() => {
        alertEl.style.transition = 'opacity .5s';
        alertEl.style.opacity = '0';
        window.setTimeout(() => alertEl.remove(), 500);
      }, 5000);
    });
  }

  function initFilterToggles() {
    document.querySelectorAll('.filter-toggle').forEach((btn) => {
      btn.addEventListener('click', () => {
        const body = btn.nextElementSibling;
        const icon = btn.querySelector('.filter-chevron');
        body?.classList.toggle('open');
        if (icon) {
          icon.style.transform = body?.classList.contains('open') ? 'rotate(180deg)' : '';
        }
      });
    });
  }

  function initSortHeaders() {
    document.querySelectorAll('th.sortable').forEach((th) => {
      th.addEventListener('click', () => {
        const url = new URL(window.location.href);
        const currentSort = url.searchParams.get('sort');
        const currentDir = url.searchParams.get('dir');
        url.searchParams.set('sort', th.dataset.col);
        url.searchParams.set('dir', currentSort === th.dataset.col && currentDir === 'asc' ? 'desc' : 'asc');
        window.location = url.toString();
      });
    });
  }

  function initClickableRows() {
    document.querySelectorAll('.clickable-row').forEach((row) => {
      row.addEventListener('click', () => {
        const parent = row.parentElement;
        const lastDragAt = Number(parent?.dataset.lastDragAt || 0);
        if (lastDragAt && Date.now() - lastDragAt < 300) {
          return;
        }
        if (row.dataset.href) {
          window.location.href = row.dataset.href;
        }
      });
    });
  }

  function initInquiryDateHelpers() {
    const inquiryDate = document.getElementById('inquiry_date');
    const followupDate = document.getElementById('followup_date');
    if (!inquiryDate || !followupDate) {
      return;
    }

    inquiryDate.addEventListener('change', () => {
      if (!followupDate.value || followupDate.dataset.autoset === 'true') {
        const nextDate = new Date(inquiryDate.value);
        nextDate.setDate(nextDate.getDate() + 10);
        followupDate.value = nextDate.toISOString().split('T')[0];
        followupDate.dataset.autoset = 'true';
      }
    });

    followupDate.addEventListener('change', () => {
      followupDate.dataset.autoset = 'false';
    });
  }

  function initReferenceButtons() {
    document.querySelectorAll('[data-add-ref]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const target = document.getElementById(btn.dataset.addRef);
        if (target) {
          target.style.display = 'grid';
          btn.style.display = 'none';
        }
      });
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    initSidebar();
    initClock();
    initAlerts();
    initFilterToggles();
    initSortHeaders();
    initClickableRows();
    initInquiryDateHelpers();
    initReferenceButtons();
  });
})();
