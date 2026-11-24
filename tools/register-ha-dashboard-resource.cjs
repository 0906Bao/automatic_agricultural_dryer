// Register only the project's frontend module. Tokens stay in memory.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const accessPath = path.join(process.env.LOCALAPPDATA, 'AutomaticAgriculturalDryer/HAOS/access.json');

async function main() {
  const access = JSON.parse(fs.readFileSync(accessPath, 'utf8'));
  const response = await fetch(access.url + '/auth/token', {
    method: 'POST', signal: AbortSignal.timeout(15000),
    body: new URLSearchParams({grant_type:'refresh_token', refresh_token:access.refresh_token, client_id:access.client_id})
  });
  if (!response.ok) throw Error(`HA authentication failed: HTTP ${response.status}`);
  const token = (await response.json()).access_token;
  const source = fs.readFileSync(path.join(root, 'home-assistant/www/dryer-status-card.js'));
  const version = crypto.createHash('sha256').update(source).digest('hex').slice(0, 12);
  const resourceUrl = '/local/dryer-status-card.js?v=' + version;
  const served = await fetch(access.url + resourceUrl, {signal:AbortSignal.timeout(15000)});
  if (!served.ok || !Buffer.from(await served.arrayBuffer()).equals(source)) throw Error('Frontend module is missing or differs from local source');
  const ws = new WebSocket(access.url.replace(/^http/, 'ws') + '/api/websocket');
  let sequence = 0;
  const pending = new Map();
  const ready = new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(Error('HA WebSocket authentication timed out')), 15000);
    ws.addEventListener('error', () => {clearTimeout(timer); reject(Error('HA WebSocket failed'));});
    ws.addEventListener('message', event => {
      const message = JSON.parse(event.data);
      if (message.type === 'auth_required') ws.send(JSON.stringify({type:'auth',access_token:token}));
      if (message.type === 'auth_ok') {clearTimeout(timer); resolve();}
      if (message.type === 'auth_invalid') {clearTimeout(timer); reject(Error('HA WebSocket authentication rejected'));}
      if (message.type === 'result' && pending.has(message.id)) {
        const task = pending.get(message.id); pending.delete(message.id); clearTimeout(task.timer);
        message.success ? task.resolve(message.result) : task.reject(Error(JSON.stringify(message.error)));
      }
    });
  });
  const command = body => new Promise((resolve, reject) => {
    const id = ++sequence;
    const timer = setTimeout(() => {pending.delete(id); reject(Error('HA command timed out'));}, 15000);
    pending.set(id, {resolve, reject, timer}); ws.send(JSON.stringify({id,...body}));
  });
  try {
    await ready;
    const resources = await command({type:'lovelace/resources'});
    const existing = resources.find(r => r.url.split('?')[0] === '/local/dryer-status-card.js');
    if (!process.argv.includes('--check')) {
      if (existing && (existing.url !== resourceUrl || existing.type !== 'module')) {
        await command({type:'lovelace/resources/update',resource_id:existing.id,url:resourceUrl,res_type:'module'});
      } else if (!existing) {
        await command({type:'lovelace/resources/create',url:resourceUrl,res_type:'module'});
      }
    }
    const after = await command({type:'lovelace/resources'});
    if (!after.some(r => r.url === resourceUrl && r.type === 'module')) throw Error('Dashboard module is not registered');
    const dashboard = await command({type:'lovelace/config',url_path:'dryer-dashboard'});
    const statusCards = dashboard.views[0].cards.filter(c => c.type === 'custom:dryer-status-card');
    if (statusCards.length !== 5) throw Error('Expected five status cards');
    if (dashboard.views[0].cards[1].title !== 'Cảnh báo') throw Error('Warning card moved away from the top');
    console.log(`Verified ${statusCards.length} status cards and module ${resourceUrl}`);
  } finally {ws.close();}
}
main().catch(error => {console.error(error.message); process.exitCode = 1;});
