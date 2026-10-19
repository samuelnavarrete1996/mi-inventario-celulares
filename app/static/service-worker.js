// service-worker.js - PWA Offline Support & Cache Management
const CACHE_NAME = 'mi-inventario-v11';
const STATIC_ASSETS = [
  '/',
  '/catalogo',
  '/manifest.json',
  '/static/css/custom.css?v=20261019_v11',
  '/static/js/app.js?v=20261019_v11',
  '/static/js/inventario.js?v=20261019_v11',
  '/static/js/pos.js?v=20261019_v11',
  '/static/js/accesorios.js?v=20261019_v11',
  '/static/js/caja.js?v=20261019_v11',
  '/static/js/garantias.js?v=20261019_v11',
  '/static/js/reportes.js?v=20261019_v11',
  '/static/js/reparaciones.js?v=20261019_v11',
  '/static/js/etiquetas_scanner.js?v=20261019_v11',
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
        keys.filter((key) => key !== CACHE_NAME).map((key) => {
          console.log('Eliminando caché antiguo:', key);
          return caches.delete(key);
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // 1. Las peticiones de API siempre van por la red para tener datos frescos
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

  // 2. Navegación HTML: NETWORK FIRST (siempre descarga el HTML nuevo del servidor si hay internet)
  if (event.request.mode === 'navigate' || (event.request.headers.get('accept') && event.request.headers.get('accept').includes('text/html'))) {
    event.respondWith(
      fetch(event.request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const copy = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          }
          return networkResponse;
        })
        .catch(() => {
          return caches.match(event.request).then((cached) => cached || caches.match('/'));
        })
    );
    return;
  }

  // 3. Recursos estáticos (CSS, JS): NETWORK FIRST para garantizar siempre la versión más reciente
  if (url.pathname.endsWith('.js') || url.pathname.endsWith('.css') || url.pathname.includes('/static/')) {
    event.respondWith(
      fetch(event.request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const copy = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
          }
          return networkResponse;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // 4. Otros recursos (imágenes, fuentes): Cache First con fallback a network
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      return cachedResponse || fetch(event.request);
    })
  );
});
