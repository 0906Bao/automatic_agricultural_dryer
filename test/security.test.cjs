const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../node-red/settings.secure.cjs'), 'utf8');
const auth = {adminUser:'admin',adminHash:'$2b$12$test',httpUser:'operator',httpHash:'$2b$12$test'};
function settings(authentication = auth) {
  const context = {module: {exports: {}}, require: file => {
    if (file === '/data/settings.js') return {credentialSecret: 'existing-encryption-key', contextStorage: {default: {module: 'memory'}}};
    if (authentication === null) throw Error('Missing auth file');
    return authentication;
  }};
  vm.runInNewContext(source, context);
  return context.module.exports;
}
test('security settings preserve existing credential encryption and protect both admin and HTTP routes', () => {
  const configured = settings();
  assert.equal(configured.credentialSecret, 'existing-encryption-key');
  assert.equal(configured.contextStorage.default.module, 'memory');
  assert.equal(configured.adminAuth.type, 'credentials');
  assert.equal(configured.adminAuth.users[0].username, 'admin');
  assert.equal(configured.adminAuth.default, undefined);
  assert.equal(configured.httpNodeAuth.user, 'operator');
  assert.equal(configured.logging.console.audit, true);
});

test('device rejection logger ignores arbitrary payloads and suppresses identical event floods', () => {
  const file=fs.readFileSync(path.join(__dirname,'../node-red/functions/security-status.js'),'utf8');
  const memory=new Map(),events=[];
  const flow={get:k=>memory.get(k),set:(k,v)=>memory.set(k,v)};
  const call=new Function('msg','flow','node',file);
  const logger={warn:message=>events.push(JSON.parse(message))};
  call({payload:'password=do-not-log'},flow,logger);
  call({payload:'REJECTED_ENVELOPE'},flow,logger);
  call({payload:'REJECTED_ENVELOPE'},flow,logger);
  assert.equal(events.length,1);
  assert.equal(events[0].reason,'REJECTED_ENVELOPE');
  assert.equal(JSON.stringify(events).includes('password'),false);
});
test('missing or malformed authentication prevents startup instead of allowing anonymous access', () => {
  assert.throws(() => settings(null), /Missing auth file/);
  assert.throws(() => settings({...auth, adminHash: ''}), /Missing authentication field/);
  assert.throws(() => settings({...auth, httpHash: 'plaintext'}), /bcrypt/);
});
