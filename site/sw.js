/* Service worker mínimo: datos, textos y código primero de la red y, sin red, la última copia; fuentes e íconos, primero la copia.
   Nunca toca POST ni /api, /oauth, /mcp, /admin, ni las páginas (llevan datos de la sesión). Sube VERSION con cada cambio del
   sitio: así la app que ya estaba abierta ofrece actualizar. */
const VERSION = "v74";
const ESTATICOS = ["/tokens.css", "/componentes.css", "/styles.css", "/base.js", "/app.js", "/charts.js", "/iconos.js",
  "/componentes.js", "/actualizar.js", "/vistas.js", "/franja.js", "/dibujo-github.svg", "/i18n/es.json", "/i18n/en.json", "/fuentes/Lexend-latin.woff2", "/icono-192.png", "/icono-512.png"];
const PROHIBIDO = /^\/(api|oauth|mcp|admin)(\/|$)/;
const FIJOS = /^\/(fuentes\/|icono-)/;

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => Promise.allSettled(ESTATICOS.map((u) => c.add(u)))).then(() => { /* sin skipWaiting aquí: la versión nueva espera el aviso de la página (actualizar.js) */ }));
});
self.addEventListener("message", (e) => { if (e.data === "SKIP_WAITING") self.skipWaiting(); });
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const r = e.request;
  const url = new URL(r.url);
  if (r.method !== "GET" || url.origin !== location.origin || PROHIBIDO.test(url.pathname)) return;
  const dato = url.pathname.endsWith("/data.json") || /\/i18n\/\w+\.json$/.test(url.pathname);
  if (!dato && !ESTATICOS.includes(url.pathname)) return;
  if (FIJOS.test(url.pathname)) {   // fuentes e íconos casi no cambian: primero la copia
    e.respondWith(caches.match(r).then((hit) => hit || fetch(r)));
    return;
  }
  // Datos, textos y código: red primero (al abrir o refrescar llega lo último); sin red, la última copia.
  e.respondWith(fetch(r).then((resp) => {
    if (resp.ok) { const copia = resp.clone(); caches.open(VERSION).then((c) => c.put(r, copia)); }
    else if (!dato && resp.status >= 500) return caches.match(r).then((hit) => hit || resp);   // el servidor falla (p. ej. al desplegar): sirve la copia
    return resp;
  }).catch(() => caches.match(r)));
});
