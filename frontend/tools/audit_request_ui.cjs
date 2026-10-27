/** Request lifecycle regressions. Run: node frontend/tools/audit_request_ui.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const { createRequire } = require('node:module');
const ts = require('typescript');
const runtime = require('react/jsx-runtime');

function harness(relative, stores, globals = {}) {
  const file = path.join(__dirname, relative);
  const localRequire = createRequire(file);
  let index = 0;
  const values = [];
  const effects = [];
  const hooks = {
    useState(initial) {
      const at = index++;
      if (!(at in values)) values[at] = typeof initial === 'function' ? initial() : initial;
      return [values[at], (next) => { values[at] = typeof next === 'function' ? next(values[at]) : next; }];
    },
    useRef(initial) { const at = index++; return values[at] ||= { current: initial }; },
    useEffect(effect) { effects.push(effect); },
    useCallback(callback) { return callback; },
  };
  const mod = { exports: {} };
  const source = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS },
  }).outputText;
  vm.runInNewContext(source, {
    exports: mod.exports, module: mod, Date, console: { log() {}, error() {} },
    require(name) {
      if (name === 'react') return hooks;
      if (name === 'react/jsx-runtime') return runtime;
      if (name.endsWith('/store')) return stores;
      if (name === 'lucide-react') return new Proxy({}, { get: () => () => null });
      if (name.endsWith('/dateUtils')) return { validDate: () => true, localDate: () => '2026-10-10' };
      return localRequire(name);
    },
    ...globals,
  });
  return { exports: mod.exports, effects, run(fn) { index = 0; effects.length = 0; return fn(); } };
}
const asStore = (state) => Object.assign((selector) => selector(state), {
  getState: () => state, setState(update) { Object.assign(state, update); },
});
const search = { searchId: null, status: 'idle', trip: { origin: null, destination: null,
  departureDate: '2026-11-01', passengerCount: 1, cabinClass: 'ECONOMY', preferredTime: 'ANY' },
  platforms: ['cleartrip'], updateTrip() {}, togglePlatform() {}, setStatus(status) { this.status = status; }, setSearchId() {} };
const result = { handoffStatus: {}, checkoutStatus: {}, offerStatus: '',
  setOfferStatus(value) { this.offerStatus = value; } };
const bot = { botStatuses: {}, botLogs: [], botScreenshots: {}, clearBotData() {}, addLog() {} };
const noopStore = asStore({});
const stores = {
  useSearchStore: asStore(search), useResultStore: asStore(result), useBotStore: asStore(bot),
  useSettingsStore: asStore({ financial: { blacklistedBanks: [], whitelistedBanks: [], allowedCardTypes: [] }, cloak: {} }),
  usePlatformStore: asStore({ platforms: [], loaded: false }), useApiStore: noopStore,
  useHistoryStore: noopStore, useLearningStore: noopStore,
};
const windowTarget = new EventTarget();
const readers = [];
class Reader {
  constructor() { readers.push(this); }
  readAsDataURL() {}
}
const cockpit = harness('../src/components/SearchCockpit.tsx', stores, {
  window: windowTarget, document: new EventTarget(), FileReader: Reader,
});
const sent = [];
function renderCockpit() {
  return cockpit.run(() => cockpit.exports.default({ sendMessage(type, payload) { sent.push({ type, payload }); } }));
}
function find(node, predicate) {
  if (!node || typeof node !== 'object') return null;
  if (predicate(node)) return node;
  for (const child of [node.props?.children].flat(Infinity)) {
    const match = find(child, predicate);
    if (match) return match;
  }
  return null;
}
let tree = renderCockpit();
const cleanups = cockpit.effects.map((effect) => effect()).filter((fn) => typeof fn === 'function');
find(tree, (node) => node.type === 'input' && node.props.placeholder?.startsWith('e.g.')).props.onChange({ target: { value: 'Delhi to Mumbai next month' } });
tree = renderCockpit();
const nlpInput = find(tree, (node) => node.type === 'input' && node.props.placeholder?.startsWith('e.g.'));
nlpInput.props.onKeyDown({ key: 'Enter' });
nlpInput.props.onKeyDown({ key: 'Enter' });
assert.equal(sent.filter((request) => request.type === 'search:nlp_parse').length, 1);
console.log('PASS repeated Enter submits one extraction');
windowTarget.dispatchEvent(new CustomEvent('request_error', { detail: { originalType: 'search:nlp_parse' } }));
nlpInput.props.onKeyDown({ key: 'Enter' });
assert.equal(sent.filter((request) => request.type === 'search:nlp_parse').length, 2);
console.log('PASS extraction can retry after a request failure');
windowTarget.dispatchEvent(new Event('nlp_parsed'));
find(tree, (node) => node.type === 'button' && node.props.children?.includes('Itinerary Vision Scan')).props.onClick();
tree = renderCockpit();
const drop = find(tree, (node) => typeof node.props?.onDrop === 'function').props.onDrop;
const dropEvent = { preventDefault() {}, dataTransfer: { files: [{ type: 'image/png' }] } };
drop(dropEvent); drop(dropEvent);
assert.equal(readers.length, 1);
readers[0].onload({ target: { result: 'data:image/png;base64,aGVsbG8=' } });
assert.equal(sent.filter((request) => request.type === 'ai:extract').length, 1);
console.log('PASS repeated image drop submits one extraction');
windowTarget.dispatchEvent(new Event('socket_disconnected'));
drop(dropEvent);
assert.equal(readers.length, 2);
readers[0].onload({ target: { result: 'data:image/png;base64,b2xk' } });
assert.equal(sent.filter((request) => request.type === 'ai:extract').length, 1);
console.log('PASS an old image reader cannot replace a retry');
windowTarget.dispatchEvent(new Event('socket_disconnected'));
readers[1].onload({ target: { result: 'data:image/png;base64,aGVsbG8=' } });
assert.equal(sent.filter((request) => request.type === 'ai:extract').length, 1);
console.log('PASS disconnect stops a pending image read from submitting');
cleanups.forEach((cleanup) => cleanup());

let socket;
class Socket {
  static OPEN = 1;
  constructor() { socket = this; this.readyState = 1; }
  send() {}
  close() {}
}
const websocket = harness('../src/hooks/useWebSocket.ts', stores, {
  window: windowTarget, WebSocket: Socket, Event, CustomEvent, alert() {},
  setTimeout() { return 1; }, clearTimeout() {},
});
const connection = websocket.run(() => websocket.exports.useWebSocket());
const stopSocket = websocket.effects[0]();
result.offerStatus = 'Refreshing public offer sources...';
socket.onmessage({ data: JSON.stringify({ type: 'error', payload: { originalType: 'coupon:refresh', message: 'Source unavailable' } }) });
assert.equal(result.offerStatus, 'Offer refresh failed: Source unavailable');
console.log('PASS global socket error resets offers without Results mounted');
result.offerStatus = 'Refreshing public offer sources...';
socket.onclose();
assert.match(result.offerStatus, /interrupted by connection loss/);
console.log('PASS global disconnect resets offers without Results mounted');
result.offerStatus = 'Refreshing public offer sources...';
connection.sendMessage('coupon:refresh', {});
assert.match(result.offerStatus, /Backend disconnected/);
console.log('PASS disconnected refresh submission clears pending status');
stopSocket();
