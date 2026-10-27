/** Regression checks for opening and verifying a booking, using installed React.
 * Run: node frontend/tools/audit_checkout_ui.cjs
 * No browser, provider request, new dependency, or application data is required.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const runtime = require('react/jsx-runtime');
const { renderToStaticMarkup } = require('react-dom/server');

const source = fs.readFileSync(path.join(__dirname, '../src/components/ResultsRanker.tsx'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS },
}).outputText;
let resultState;
let buttons = [];
let effects = [];
const eventHub = new EventTarget();
const intervals = new Map();
const effectReact = { ...React, useEffect(effect) { effects.push(effect); } };
const searchState = { status: 'completed' };
const store = (read) => Object.assign((select) => select(read()), { getState: read });
const stores = {
  useResultStore: store(() => resultState),
  useSearchStore: store(() => searchState),
  useBotStore: store(() => ({ botStatuses: {} })),
};
const capturedRuntime = Object.fromEntries(Object.entries(runtime).map(([key, value]) => [key,
  ['jsx', 'jsxs'].includes(key) ? (type, props, ...args) => {
    if (type === 'button') buttons.push(props);
    return value(type, props, ...args);
  } : value,
]));
const componentModule = { exports: {} };
vm.runInNewContext(compiled + '\nexports.receiptIsCurrent = currentReceipt;', {
  exports: componentModule.exports,
  module: componentModule,
  require(name) {
    if (name === '../store') return stores;
    if (name === 'react') return effectReact;
    if (name === 'react/jsx-runtime') return capturedRuntime;
    if (name.startsWith('./')) return { default: () => null, __esModule: true };
    return require(name);
  },
  Date,
  console,
  window: eventHub,
  setInterval(callback, delay) { const id = intervals.size + 1; intervals.set(id, { callback, delay }); return id; },
  clearInterval(id) { intervals.delete(id); },
});
const Component = componentModule.exports.default;
const listing = {
  id: 'listing', search_id: 'search', platform: 'cleartrip', airline: 'IndiGo',
  flight_number: '6E123', departure_date: '2026-11-01', departure_time: '10:00',
  arrival_time: '12:00', duration: '2h', stops: 0, base_price: 4000,
  final_price: 4000, effective_price: 4000, savings: 0,
  savings_breakdown: { verification: 'listed', origin: 'DEL', destination: 'BOM',
    integrity: { status: 'uncorroborated' } },
};
function render(sessionId, handoffStatus, verification = 'listed', additionalRows = []) {
  buttons = [];
  effects = [];
  const sent = [];
  resultState = {
    results: [{ ...listing, session_id: sessionId, savings_breakdown: {
      ...listing.savings_breakdown, verification, observed_at: '2020-01-01T00:00:00Z',
    } }, ...additionalRows],
    dealOptions: null, alternatives: [], suggestions: null, handoffStatus,
    checkoutStatus: {}, offers: {}, couponTrackRecord: {}, offerStatus: '',
    setCheckoutStatus(id, status) { resultState.checkoutStatus[id] = status; },
    setOfferStatus(status) { resultState.offerStatus = status; },
  };
  const html = renderToStaticMarkup(React.createElement(Component, {
    sendMessage(type, payload) { sent.push({ type, payload }); },
  }));
  return { html, sent };
}
for (const [name, sessionId, handoff, verification, expected] of [
  ['listing before opening has no verification button', null, {}, 'listed', false],
  ['first listed cart can be verified', 'cart', { cart: 'success' }, 'listed', true],
  ['stale receipt can be reverified', 'cart', { cart: 'success' }, 'checkout', true],
  ['failed handoff cannot be verified', 'cart', { cart: 'failed' }, 'checkout', false],
  ['pending handoff cannot be verified', 'cart', { cart: 'pending' }, 'listed', false],
]) {
  const { html } = render(sessionId, handoff, verification);
  assert.equal(html.includes('Verify total &amp; coupons'), expected, name);
  console.log('PASS ' + name);
}
for (const [name, sessionId, handoff] of [
  ['new cart uses preparation', null, {}],
  ['active cart uses reusable preparation', 'cart', { cart: 'success' }],
  ['expired cart can request preparation again', 'cart', { cart: 'failed' }],
]) {
  const { sent } = render(sessionId, handoff);
  const openButton = buttons.find((button) => button.children === 'Open booking');
  assert.ok(openButton && !openButton.disabled, name);
  openButton.onClick();
  assert.equal(sent.length, 1, name);
  assert.equal(sent[0].type, 'session:prepare', name);
  assert.equal(sent[0].payload.searchId, 'search', name);
  assert.equal(sent[0].payload.resultId, 'listing', name);
  console.log('PASS ' + name);
}
const { sent } = render('cart', { cart: 'success' });
buttons.find((button) => button.children === 'Verify total & coupons').onClick();
assert.equal(sent[0].type, 'session:verify');
assert.equal(sent[0].payload.sessionId, 'cart');
assert.equal(resultState.checkoutStatus.cart.status, 'running');
console.log('PASS first verification submits the active cart');

// Execute the registered lifecycle effect against a real EventTarget. Keep the
// remaining effects isolated so these checks do not initiate coupon requests.
render('cart', { cart: 'success' }, 'checkout');
const stopLifecycle = effects[0]();
resultState.offerStatus = 'Refreshing public offer sources...';
eventHub.dispatchEvent(new CustomEvent('request_error', {
  detail: { originalType: 'coupon:refresh', message: 'Source unavailable' },
}));
assert.equal(resultState.offerStatus, 'Offer refresh failed: Source unavailable');
console.log('PASS coupon refresh error clears pending status');
resultState.offerStatus = 'Refreshing public offer sources...';
eventHub.dispatchEvent(new Event('socket_disconnected'));
assert.match(resultState.offerStatus, /interrupted by connection loss/);
console.log('PASS connection loss clears coupon refresh status');
stopLifecycle();

const stopReceiptClock = effects[1]();
assert.equal(intervals.size, 1);
assert.equal([...intervals.values()][0].delay, 30_000);
stopReceiptClock();
assert.equal(intervals.size, 0);
console.log('PASS receipt clock is scheduled and cleaned up');

const observed = Date.parse('2026-10-10T10:00:00Z');
const receipt = { ...listing, session_id: 'cart', savings_breakdown: {
  ...listing.savings_breakdown, verification: 'checkout', observed_at: new Date(observed).toISOString(),
} };
assert.equal(componentModule.exports.receiptIsCurrent(receipt, { cart: 'success' }, observed + 899_999), true);
assert.equal(componentModule.exports.receiptIsCurrent(receipt, { cart: 'success' }, observed + 900_000), false);
console.log('PASS receipt freshness ends at fifteen minutes');

const current = { ...listing, id: 'current', airline: 'Current airline', session_id: 'fresh',
  final_price: 5000, savings_breakdown: { ...listing.savings_breakdown,
    verification: 'checkout', observed_at: new Date().toISOString() } };
const comparison = render('cart', { cart: 'success', fresh: 'success' }, 'checkout', [current]);
assert.ok(comparison.html.indexOf('Current airline') < comparison.html.indexOf('IndiGo'));
assert.ok(comparison.html.includes('Recorded payment total'));
assert.ok(comparison.html.includes('Lowest verified total among these results'));
console.log('PASS current receipts rank before stale records and stale amount is labeled');
