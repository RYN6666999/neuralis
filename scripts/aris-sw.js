/* Aris chat — minimal service worker.
   App-shell cache for install + fast load. API calls always go to network. */
const CACHE = 'aris-shell-v3';
const SHELL = ['/', '/manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;                       // POST /c → network, untouched
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  // never cache live API surfaces
  if (/^\/(c|events|health|admin|conversations)\b/.test(url.pathname)) return;

  // app shell: cache-first, refresh in background
  e.respondWith(
    caches.match(req).then(hit => {
      const net = fetch(req).then(res => {
        if (res && res.ok) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
        return res;
      }).catch(() => hit);
      return hit || net;
    })
  );
});
