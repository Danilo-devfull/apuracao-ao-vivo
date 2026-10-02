// Service worker mínimo: permite instalar o atalho e abre a página mesmo com internet instável.
// Os resultados (/api/) NUNCA vêm do cache do aparelho: sempre ao vivo.
const CACHE = 'apuracao-v38';
const BASE = ['/', '/static/app.css', '/static/app.js', '/static/icone-192.png', '/static/banner-768.webp'];
self.addEventListener('install', e => { e.waitUntil(caches.open(CACHE).then(c => c.addAll(BASE))); self.skipWaiting(); });
self.addEventListener('activate', e => e.waitUntil(
  caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k)))).then(() => self.clients.claim())
));
self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin || url.pathname.startsWith('/api/') || url.pathname.startsWith('/painel')) return;
  e.respondWith(fetch(e.request).then(r => {
    if (r.ok && BASE.includes(url.pathname)) { const c = r.clone(); caches.open(CACHE).then(cc => cc.put(e.request, c)); }
    return r;
  }).catch(() => caches.match(e.request)));
});