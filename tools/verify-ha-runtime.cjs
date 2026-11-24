const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const access=JSON.parse(fs.readFileSync(path.join(process.env.LOCALAPPDATA,'AutomaticAgriculturalDryer/HAOS/access.json'),'utf8'));
const auth={Authorization:'Bearer '+access.access_token};
async function get(url,headers=auth){const response=await fetch(url,{headers});assert.ok(response.ok,`HTTP ${response.status}: ${url}`);return response.json();}
function websocket(command){return new Promise((resolve,reject)=>{
  const ws=new WebSocket(access.url.replace(/^http/,'ws')+'/api/websocket');
  const timer=setTimeout(()=>{ws.close();reject(Error('HA WebSocket timeout'));},15000);
  ws.addEventListener('message',event=>{
    const m=JSON.parse(event.data);
    if(m.type==='auth_required')ws.send(JSON.stringify({type:'auth',access_token:access.access_token}));
    else if(m.type==='auth_ok')ws.send(JSON.stringify({id:1,...command}));
    else if(m.type==='result'){clearTimeout(timer);ws.close();m.success?resolve(m.result):reject(Error(JSON.stringify(m.error)));}
  });
  ws.addEventListener('error',()=>{clearTimeout(timer);reject(Error('HA WebSocket error'));});
});}
function canonical(value){if(Array.isArray(value))return value.map(canonical);if(value&&typeof value==='object')return Object.fromEntries(Object.keys(value).sort().map(key=>[key,canonical(value[key])]));return value;}
(async()=>{
  const states=await get(access.url+'/api/states');const ids=new Set(states.map(s=>s.entity_id));
  const required=['sensor.dryer_temperature','sensor.dryer_humidity','sensor.dryer_rain_adc','binary_sensor.dryer_rain',
    'sensor.dryer_light_adc','binary_sensor.dryer_dark','binary_sensor.dryer_humidity_warning','binary_sensor.dryer_humidity_danger',
    'binary_sensor.dryer_dht_valid','binary_sensor.dryer_limit_closed','binary_sensor.dryer_limit_open',
    'sensor.dryer_cover_request','sensor.dryer_cover_reason','cover.dryer_roof'];
  for(const id of required)assert.ok(ids.has(id),'Missing required entity: '+id);
  assert.ok(!states.some(s=>s.entity_id.includes('.dryer_smoke_')),'Temporary test states remain');
  const dashboard=await websocket({type:'lovelace/config',url_path:'dryer-dashboard'});
  const refs=new Set();
  function collect(v){if(typeof v==='string'&&/^(sensor|binary_sensor|cover|button|script)\.dryer_/.test(v))refs.add(v);
    else if(Array.isArray(v))v.forEach(collect);else if(v&&typeof v==='object')Object.values(v).forEach(collect);}
  collect(dashboard);for(const id of refs)assert.ok(ids.has(id),'Dashboard entity missing: '+id);
  const banner=dashboard.views[0].cards.find(card=>card.type==='markdown'&&card.content.includes('TỰ ĐỘNG ĐANG BẬT'));
  let renderedMode=null;
  if(banner){
    const rendered=await fetch(access.url+'/api/template',{method:'POST',headers:{...auth,'Content-Type':'application/json'},body:JSON.stringify({template:banner.content})});
    assert.ok(rendered.ok,'Automatic mode banner template did not render');
    renderedMode=(await rendered.text()).split('\n').find(line=>line.startsWith('## '));
  }
  const entries=await get(access.url+'/api/config/config_entries/entry');const broker=entries.find(e=>e.domain==='mqtt');
  assert.ok(broker&&broker.state==='loaded','MQTT integration not loaded');
  const earliest=fs.readdirSync(path.join(root,'backups')).filter(name=>/^node-red-\d+-\d+$/.test(name)).sort()[0];
  assert.ok(earliest,'No Node-RED baseline backup found');
  const before=JSON.parse(fs.readFileSync(path.join(root,'backups',earliest,'flows-before.json'),'utf8').replace(/^\uFEFF/,''));
  const current=await get('http://localhost:1880/flows',{'Node-RED-API-Version':'v2'});
  for(const node of before.flows){const after=current.flows.find(n=>n.id===node.id);assert.deepEqual(canonical(after),canonical(node),'Existing Node-RED node changed: '+node.id);}
  assert.ok(!current.flows.some(n=>n.id.startsWith('smoke-')),'Temporary test nodes remain');
  const front=await fetch(access.url+'/');assert.equal(front.status,200);
  let lanStatus='not reachable from host';
  try{const lan=await fetch('http://192.168.1.4:8123/',{signal:AbortSignal.timeout(5000)});lanStatus=lan.status;}catch(_){}
  const report={required_entities:required.length,dashboard_references:refs.size,mqtt:broker.state,
    auto_status:states.find(state=>state.entity_id==='sensor.dryer_auto_status')?.state,
    auto_enabled:states.find(state=>state.entity_id==='binary_sensor.dryer_auto_enabled')?.state,
    rendered_mode_banner:renderedMode,
    original_nodes_preserved:before.flows.length,temporary_test_states:0,frontend_http:front.status,lan_http_from_host:lanStatus,
    phone_test:'not verified on a physical phone',firmware_hardware:'not flashed/tested'};
  fs.writeFileSync(path.join(root,'.local/ha-final-verification.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
})().catch(error=>{console.error(error.message);process.exitCode=1;});
