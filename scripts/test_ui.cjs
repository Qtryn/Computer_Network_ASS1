// Exercises the real page script with a tiny DOM double. This is not a browser E2E test.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

class Element {
  constructor() { this.value = ''; this.children = []; this.elements = []; this.handlers = {}; this.files = []; }
  addEventListener(name, callback) { this.handlers[name] = callback; }
  appendChild(child) { this.children.push(child); }
  replaceChildren(...children) { this.children = children; this.value = children[0]?.value || ''; }
  add(child) { this.children.push(child); }
}

async function main() {
  const html = fs.readFileSync(path.join(__dirname, '../app/web/static/index.html'), 'utf8');
  const elements = Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m => [m[1], new Element()]));
  elements['chat-form'].elements = [elements.message, new Element()];
  elements['file-form'].elements = [elements.file, new Element()];
  let state = {username:'alice', connected:false, account_mode:true, online:[], events:[], last_id:0, session_id:null};
  let failLogin = false;
  let deferred = null;
  const requests = [];
  const context = vm.createContext({
    document: {getElementById: id => elements[id], createElement: () => new Element()},
    Option: function(text, value) { this.textContent = text; this.value = value; },
    setInterval() {},
    fetch: async (url, options) => {
      requests.push({url, options});
      if (deferred && url.startsWith('/api/state')) return deferred;
      if (url === '/api/login') {
        if (failLogin) return {ok:false, json:async () => ({error:'Invalid username or password'})};
        state = {...state, connected:true, online:['alice','bob'], session_id:'fresh',
          events:[{id:1, type:'INFO', message:'Logged in as alice'}], last_id:1};
      }
      if (url === '/api/logout') state = {...state, connected:false, online:[], session_id:null, events:[], last_id:0};
      return {ok:true, json:async () => url.startsWith('/api/state') ? structuredClone(state) : {ok:true}};
    },
  });
  vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1], context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(elements.password.hidden, false);
  assert.equal(elements['login-form'].hidden, false);
  assert.equal(elements.message.disabled, true);
  elements.password.value = 'typing-password';
  await vm.runInContext('refresh()', context);
  assert.equal(elements.password.value, 'typing-password', 'polling must preserve a password being typed');

  failLogin = true;
  await elements['login-form'].handlers.submit({preventDefault(){}});
  assert.equal(elements.password.value, '');
  assert.match(elements.status.textContent, /Invalid username or password/);
  await vm.runInContext('refresh()', context);
  assert.match(elements.status.textContent, /Invalid username or password/);

  failLogin = false;
  elements.password.value = 'demo-secret';
  await elements['login-form'].handlers.submit({preventDefault(){}});
  assert.equal(elements['login-form'].hidden, true);
  assert.equal(elements.message.disabled, false);
  assert.equal(elements.password.value, '');
  state.events.push({id:2, type:'CHAT', sender:'bob', recipient:'alice', text:'old history'});
  state.last_id = 2;
  await vm.runInContext('refresh()', context);
  assert(elements.feed.children.some(line => line.textContent.includes('old history')));
  elements.progress.value = 85;
  elements.recipient.value = 'bob';
  await elements.logout.handlers.click();
  assert.equal(elements.feed.children.length, 0);
  assert.equal(elements.progress.value, 0);
  assert.equal(elements.recipient.value, '*');
  assert.equal(vm.runInContext('cursor', context), 0);
  assert.equal(elements.message.disabled, true);

  await elements['login-form'].handlers.submit({preventDefault(){}});
  assert(!elements.feed.children.some(line => line.textContent.includes('old history')));
  assert.equal(vm.runInContext('cursor', context), 1);
  // An old poll must not repopulate the DOM after logout changes the generation.
  let resolvePoll;
  deferred = new Promise(resolve => { resolvePoll = resolve; });
  const refresh = vm.runInContext('refresh()', context);
  vm.runInContext('generation++; clearSession()', context);
  resolvePoll({ok:true, json:async () => ({...state, events:[{id:99, type:'CHAT', sender:'bob', text:'stale'}]})});
  await refresh;
  assert.equal(elements.feed.children.length, 0);
  assert.equal(vm.runInContext('cursor', context), 0);
  assert.match(html, /id="password" type="password"/);
  assert(!/localStorage|sessionStorage/.test(html));
  assert(requests.some(r => r.url === '/api/login'));
  console.log('PASS: UI script login/error, password clearing, polling, logout reset, relogin and stale-response guards (DOM double; no browser)');
}

main().catch(error => { console.error(error); process.exitCode = 1; });
