(function () {
  const HeavyLift = (window.HeavyLift = window.HeavyLift || {});
  const csrfMeta = document.querySelector('meta[name="csrf-token"]');

  HeavyLift.csrfToken = csrfMeta?.getAttribute('content') || '';
  HeavyLift.escHtml = function escHtml(str) {
    if (!str) {
      return '';
    }
    return str.replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  };

  const originalFetch = window.fetch.bind(window);
  window.fetch = (input, init = {}) => {
    const method = (init.method || input?.method || 'GET').toUpperCase();
    const requestUrl = typeof input === 'string' ? input : input?.url || window.location.href;
    const url = new URL(requestUrl, window.location.origin);
    if (url.origin !== window.location.origin || ['GET', 'HEAD', 'OPTIONS', 'TRACE'].includes(method)) {
      return originalFetch(input, init);
    }

    const headers = new Headers(init.headers || input?.headers || {});
    if (HeavyLift.csrfToken && !headers.has('X-CSRF-Token')) {
      headers.set('X-CSRF-Token', HeavyLift.csrfToken);
    }
    return originalFetch(input, { ...init, headers });
  };
})();
