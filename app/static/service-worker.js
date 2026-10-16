// service-worker.js - PWA Offline Support & Cache Management
const CACHE_NAME = 'mi-inventario-v2';
const STATIC_ASSETS = [
  '/',
  '/static/css/custom.css?v=20261016_v2',
  '/static/js/app.js?v=20261016_v2',
  '/static/js/inventario.js?v=20261016_v2',
  '/static/js/pos.js?v=20261016_v2',
  '/static/js/accesorios.js?v=20261016_v2',
  '/static/js/caja.js?v=20261016_v2',
  '/static/js/garantias.js?v=20261016_v2',
  '/static/js/reportes.js?v=20261016_v2',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS).catch((err) => {
        console.warn('Advertencia precacheando assets:', err);
      });
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Las peticiones de API siempre van por la red para tener datos 100% frescos
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request).catch(() => {
        return new Response(JSON.stringify({ error: 'Sin conexión a internet' }), {
          status: 503,
          headers: { 'Content-Type': 'application/json' }
        });
      })
    );
    return;
  }

  // Recursos estáticos: Stale-While-Revalidate (devuelve caché rápido y actualiza en segundo plano)
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      const fetchPromise = fetch(event.request).then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200 && networkResponse.type === 'basic') {
          const responseToCache = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseToCache);
          });
        }
        return networkResponse;
      }).catch(() => cachedResponse);

      return cachedResponse || fetchPromise;
    })
  );
});
