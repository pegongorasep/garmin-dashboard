// Comprueba el orden de respuestas sin navegador ni llamadas de red.
const fs = require('fs'), vm = require('vm'), assert = require('assert');
const entradas = [], eventos = [], solicitudes = [];
function nodo() {
  return {dataset: {}, style: {}, hidden: false, classList: {toggle() {}},
    append(...xs) { this.hijos = (this.hijos || []).concat(xs); }, prepend(x) { entradas.push(x); },
    setAttribute() {}, closest() { return null; }};
}
global.window = {dispatchEvent(e) { eventos.push(e); return true; }, matchMedia() { return false; }};
global.matchMedia = window.matchMedia;
global.location = {pathname: '/'};
global.document = {currentScript: {dataset: {campo: 'csrf', solicitando: 'SOLICITANDO', fallo: 'ERROR'}},
  body: nodo(), documentElement: {}, createElement: nodo, getElementById() { return null; },
  querySelector() { return null; }, addEventListener() {}, hidden: false};
global.CustomEvent = class { constructor(type, args) { this.type = type; this.detail = args.detail; } };
global.requestAnimationFrame = () => 1; global.cancelAnimationFrame = () => {};
global.setTimeout = () => 1; global.clearTimeout = () => {};
global.fetch = (url, opts) => new Promise((resolve, reject) => solicitudes.push({opts, resolve, reject}));
vm.runInThisContext(fs.readFileSync(process.argv[2], 'utf8'));
const tick = () => new Promise(resolve => setImmediate(resolve));
(async () => {
  assert.equal(solicitudes.length, 1); // GET iniciado antes del clic
  const primera = window.Franja.empezar('normal');
  window.Franja.empezar('normal');
  assert.equal(solicitudes.length, 2);
  assert.equal(window.Franja.viva(), true);
  assert.equal(entradas[0].hijos[0].hijos[0].textContent, 'SOLICITANDO');
  solicitudes[0].resolve({ok: true, json: async () => ({sinc: null})});
  await tick();
  assert.equal(window.Franja.viva(), true); // GET viejo no borra el estado inmediato
  solicitudes[1].resolve({ok: false, status: 403, json: async () => ({error: 'sin_instalacion'})});
  await primera;
  assert.equal(window.Franja.viva(), false);
  assert.equal(entradas[0].hijos[0].hijos[0].textContent, 'ERROR');
  const segunda = window.Franja.empezar('normal');
  assert.equal(solicitudes.length, 3);
  solicitudes[2].reject(new Error('offline'));
  await segunda;
  assert.equal(window.Franja.viva(), false);
  const tercera = window.Franja.empezar('normal');
  assert.equal(solicitudes.length, 4);
  solicitudes[3].resolve({ok: true, status: 200, json: async () => ({sinc: {estado:'corriendo', texto:'REAL', porcentaje: 20}})});
  await tercera;
  assert.equal(entradas[0].hijos[0].hijos[0].textContent, 'REAL');
  assert.equal(window.Franja.viva(), true);
})().catch(e => { console.error(e); process.exitCode = 1; });
