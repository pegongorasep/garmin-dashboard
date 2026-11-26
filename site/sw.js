/* Service worker mínimo: guarda lo estático; data.json y los textos (i18n/*.json) primero de la red y, sin red, la última copia.
   Nunca toca POST ni /api, /oauth, /mcp, /admin, ni las páginas (llevan datos de la sesión). */
const VERSION = "v12";
const ESTATICOS = ["/tokens.css", "/componentes.css", "/styles.css", "/base.js", "/app.js", "/charts.js", "/iconos.js",
  "/componentes.js", "/vistas.js", "/i18n/es.json", "/i18n/en.json", "/fuentes/Lexend-latin.woff2", "/icono-192.png", "/icono-512.png"];
const PROHIBIDO = /^\/(api|oauth|mcp|admin)(\/|$)/;

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(VERSION).then((c) => Promise.allSettled(ESTATICOS.map((u) => c.add(u)))).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== VERSION).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});
self.addEventListener("fetch", (e) => {
  const r = e.request;
  const url = new URL(r.url);
  if (r.method !== "GET" || url.origin !== location.origin || PROHIBIDO.test(url.pathname)) return;
  if (url.pathname.endsWith("/data.json") || /\/i18n\/\w+\.json$/.test(url.pathname)) {   // los textos, como data.json: red primero
    e.respondWith(fetch(r).then((resp) => {
      if (resp.ok) { const copia = resp.clone(); caches.open(VERSION).then((c) => c.put(r, copia)); }
      return resp;
    }).catch(() => caches.match(r)));
    return;
  }
  if (ESTATICOS.includes(url.pathname)) {
    e.respondWith(caches.match(r).then((hit) => hit || fetch(r)));
  }
});
