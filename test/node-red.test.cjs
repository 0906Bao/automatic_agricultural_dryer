const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {execFileSync} = require('node:child_process');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
function harness() {
  const memory = new Map();
  const flow = {get: key => memory.get(key), set:(key,val) => memory.set(key,val)};
  const call = (file, msg) => new Function('msg', 'flow', fs.readFileSync(path.join(root, 'node-red/functions', file+'.js'),'utf8'))(msg, flow);
  return {flow, call};
}
function telemetry(h) { h.call('cache', {payload:{session:'deadbeef', last_command_seq:7, dht_valid:true}}); }
test('cache rejects malformed telemetry and state reports offline before first packet', () => {
  const h = harness(); h.call('cache',{payload:{session:'bad',last_command_seq:1}});
  assert.equal(h.call('state',{}).payload.online,false);
  telemetry(h); assert.equal(h.call('state',{}).payload.online,true);
  h.flow.get('dryerState').receivedAt -= 11000;
  assert.equal(h.call('state',{}).payload.online,false);
});
test('commands require fresh telemetry and reject unknown commands', () => {
  const h = harness();
  assert.equal(h.call('command',{payload:{command:'OPEN'}})[1].statusCode,409);
  telemetry(h);
  assert.equal(h.call('command',{payload:{command:'REBOOT'}})[1].statusCode,400);
  h.flow.get('dryerState').receivedAt -= 11000;
  assert.equal(h.call('command',{payload:{command:'AUTO'}})[0],null);
});
test('all commands are non-retained with monotonic session envelope and HTTP request preserved', () => {
  const h = harness(); telemetry(h); let previous = 0;
  for (const command of ['STOP','AUTO','OPEN','CLOSE','RESET']) {
    const req = {}, res = {};
    const [mqtt,http] = h.call('command',{payload:{command},req,res});
    assert.equal(mqtt.retain,false); assert.equal(mqtt.topic,'dryer/command');
    assert.equal(http.statusCode,202); assert.equal(http.req,req); assert.equal(http.res,res);
    const [session,seq,verb] = mqtt.payload.split(' ');
    assert.equal(session,'deadbeef'); assert.equal(verb,command);
    assert.ok(Number(seq)>previous); previous=Number(seq);
    assert.equal(http.payload.sequence,Number(seq));
  }
});
test('sequence advances beyond last accepted device command', () => {
  const h = harness(); telemetry(h);
  h.flow.get('dryerState').data.last_command_seq = Date.now()+1000000;
  const [msg] = h.call('command',{payload:{command:'STOP'}});
  assert.ok(Number(msg.payload.split(' ')[1]) > h.flow.get('dryerState').data.last_command_seq);
});
test('flow export matches source and every wire resolves', () => {
  execFileSync(process.execPath,['tools/build-flow.cjs','--check'],{cwd:root});
  const nodes=JSON.parse(fs.readFileSync(path.join(root,'node-red/flows.json'),'utf8'));
  const ids=new Set(nodes.map(n=>n.id));
  assert.equal(ids.size,nodes.length);
  for(const node of nodes) for(const outputs of node.wires||[]) for(const id of outputs) assert.ok(ids.has(id));
  assert.equal(nodes.find(n=>n.id==='command-out').retain,'false');
  const html=nodes.find(n=>n.id==='page').template;
  assert.ok(html.includes('textContent')); assert.ok(!html.includes('innerHTML'));
  new Function(html.match(/<script>([\s\S]*?)<\/script>/)[1]);
});
function browser(telemetry, online = true) {
  const elements = new Map();
  const element = () => ({textContent:'',dataset:{},disabled:true,classList:{toggle(){},remove(){}}});
  const buttons = ['STOP','AUTO','OPEN','CLOSE','RESET'].map(command => {
    const b=element(); b.dataset.command=command; b.addEventListener=(_,fn)=>b.click=fn; return b;
  });
  const requests=[];
  const context = vm.createContext({
    document:{getElementById(id){if(!elements.has(id)) elements.set(id,element());return elements.get(id);},querySelectorAll(){return buttons;}},
    AbortSignal, setInterval(){},
    fetch:async(url,opts)=>{
      requests.push({url,opts});
      return {ok:true,json:async()=>url.endsWith('/state') ? {online,age_ms:100,telemetry} :
        {queued:JSON.parse(opts.body).command,session:'deadbeef',sequence:10}};
    }
  });
  const html=fs.readFileSync(path.join(root,'node-red/dashboard.html'),'utf8');
  vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);
  return {context,elements,buttons,requests};
}
test('dashboard hides invalid/stale DHT data and locks controls offline', async()=>{
  const b=browser({dht_valid:true,temperature_c:30,humidity_pct:60},false);
  await b.context.refresh();
  assert.equal(b.elements.get('temperature').textContent,'Không hợp lệ');
  assert.ok(b.buttons.every(button=>button.disabled));
  const live=browser({dht_valid:false,temperature_c:30,humidity_pct:60},true);
  await live.context.refresh();
  assert.equal(live.elements.get('humidity').textContent,'Không hợp lệ');
  assert.ok(live.buttons.every(button=>!button.disabled));
});
test('dashboard sends explicit command on click and waits for device acknowledgement',async()=>{
  const b=browser({session:'deadbeef',last_command_seq:0,dht_valid:true,temperature_c:30,humidity_pct:60},true);
  await b.context.refresh();
  await b.buttons.find(button=>button.dataset.command==='AUTO').click();
  const request=b.requests.find(request=>request.url.endsWith('/command'));
  assert.deepEqual(JSON.parse(request.opts.body),{command:'AUTO'});
  assert.match(b.elements.get('message').textContent,/chờ thiết bị/);
});
