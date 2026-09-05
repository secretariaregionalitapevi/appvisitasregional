const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const values = new Map(), handlers = new Map(), windowEvents = new Map();
let ready, active = '#pendentes', fetches = 0;
const location = {hash: ''};
const tabs = ['#pendentes', '#usuarios', '#auditoria', '#sessoes'].map(href => ({
  getAttribute: () => href,
  addEventListener(name, fn) {this[name] = fn;},
}));
const document = {
  querySelectorAll: () => tabs,
  querySelector: selector => selector.includes('.nav-link.active') ? tabs.find(tab => tab.getAttribute() === active) : {},
};
function $(selector) {
  if (typeof selector === 'function') {ready = selector; return;}
  return {
    on(events, filter, fn) {handlers.set(String(selector) + ':' + events, fn || filter); return this;},
    val() {return '';},
    html(value) {values.set(selector, value); return this;},
    text() {return this;}, prop() {return this;}, addClass() {return this;}, removeClass() {return this;},
  };
}
const profiles = Array.from({length:120}, (_, i) => ({user_id: String(i), full_name:'Pessoa '+i, status:'approved'}));
const context = {
  $, document, location, console, setTimeout, clearTimeout, AbortController,
  window: {addEventListener: (name, fn) => windowEvents.set(name, fn)},
  history: {pushState: (_a, _b, hash) => {location.hash = hash;}},
  bootstrap: {Tab: {getOrCreateInstance: tab => ({show() {
    if (active === tab.getAttribute()) return;
    active = tab.getAttribute(); tab['shown.bs.tab']?.();
  }})}},
  fetch: async () => {fetches++; return {ok: true, headers: {get: () => 'application/json'},
    json: async () => ({profiles, logs: [], sessions: [], module_access: [], access_levels: []})};},
};
(async () => {
  vm.runInNewContext(fs.readFileSync('static/js/admin/auditoria.js', 'utf8'), context);
  ready();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(values.has('#users-table'), false, 'Hidden tables should not render on initial load');
  location.hash = '#usuarios'; windowEvents.get('hashchange')();
  assert.equal(active, '#usuarios');
  assert.equal((values.get('#users-table').match(/<tr>/g) || []).length, 50);
  assert.match(values.get('#usuarios-pagination'), /120/);
  handlers.get('[object Object]:click').call({dataset:{section:'usuarios', page:'3'}});
  assert.equal((values.get('#users-table').match(/<tr>/g) || []).length, 20);
  location.hash = '#sessoes'; windowEvents.get('popstate')();
  assert.equal(active, '#sessoes');
  assert.ok(values.has('#sessions-table'));
  tabs[2]['shown.bs.tab']();
  assert.equal(location.hash, '#auditoria', 'Clicking a tab should update the URL');
  location.hash = '#invalid'; windowEvents.get('hashchange')();
  assert.equal(active, '#sessoes', 'Invalid hashes should not activate unknown content');
  assert.equal(fetches, 1, 'Switching tabs must reuse loaded data');
  console.log('OK: sidebar hash navigation, history, lazy rendering, pagination, and data reuse');
})().catch(error => {console.error(error); process.exitCode = 1;});
