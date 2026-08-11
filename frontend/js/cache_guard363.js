(() => {
  'use strict';
  const BUILD = '3630';
  const KEY = 'pichat_client_build';
  const RELOAD_KEY = 'pichat_cache_refresh_3630';

  async function refreshClientCache() {
    let previous = null;
    try { previous = localStorage.getItem(KEY); } catch (_) {}
    if (previous === BUILD) return;

    try { localStorage.setItem(KEY, BUILD); } catch (_) {}

    try {
      if ('caches' in window) {
        const keys = await caches.keys();
        await Promise.all(
          keys
            .filter(k => /^pichat-/i.test(k))
            .map(k => caches.delete(k))
        );
      }
    } catch (_) {}

    try {
      if ('serviceWorker' in navigator) {
        const regs = await navigator.serviceWorker.getRegistrations();
        await Promise.all(
          regs
            .filter(r => {
              const u = r.active?.scriptURL || r.waiting?.scriptURL || r.installing?.scriptURL || '';
              return !u || u.startsWith(location.origin);
            })
            .map(r => r.unregister())
        );
      }
    } catch (_) {}

    // Un seul rechargement forcé, en onglet normal.
    try {
      if (sessionStorage.getItem(RELOAD_KEY) !== '1') {
        sessionStorage.setItem(RELOAD_KEY, '1');
        const url = new URL(location.href);
        url.searchParams.set('_pichat', BUILD);
        location.replace(url.toString());
      } else {
        sessionStorage.removeItem(RELOAD_KEY);
      }
    } catch (_) {
      location.reload();
    }
  }

  refreshClientCache();
})();