# PWA Configuration - Progressive Web App Setup

## Service Worker (static/sw.js)
```javascript
const CACHE_NAME = 'fantacalcio-ai-v1';
const urlsToCache = [
  '/',
  '/static/css/style.css',
  '/static/js/app.js',
  '/static/images/logo.png',
  '/static/images/icon-192.png',
  '/static/images/icon-512.png'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});
```

## Web Manifest (static/manifest.json)
```json
{
  "name": "FantaCalcio AI Assistant",
  "short_name": "FantaCalcio AI",
  "description": "Consigli per asta, formazioni e strategie",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#1a73e8",
  "icons": [
    {
      "src": "/static/images/icon-192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/static/images/icon-512.png",
      "sizes": "512x512",
      "type": "image/png"
    }
  ]
}
```

## Meta Tags (add to templates/index.html)
```html
<link rel="manifest" href="/static/manifest.json">
<meta name="theme-color" content="#1a73e8">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black">
<meta name="apple-mobile-web-app-title" content="FantaCalcio AI">
<link rel="apple-touch-icon" href="/static/images/icon-192.png">
```
