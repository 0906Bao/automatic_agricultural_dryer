const test=require('node:test'), assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path');
const root=path.resolve(__dirname,'..');
test('Wokwi end stops retain state and preserve active-low GPIO18/19 wiring',()=>{
  const diagram=JSON.parse(fs.readFileSync(path.join(root,'diagram.json'),'utf8'));
  const connected=(a,b)=>diagram.connections.some(([x,y])=>(x===a&&y===b)||(x===b&&y===a));
  for(const [id,pin] of [['limitClose','D18'],['limitOpen','D19']]){
    const part=diagram.parts.find(p=>p.id===id);
    assert.equal(part.type,'wokwi-slide-switch');
    assert.equal(part.attrs.value,''); // boots released, not falsely at an endpoint
    assert.ok(connected(id+':2','esp:'+pin));
    assert.ok(connected(id+':3','esp:GND.1')); // right = grounded = active
    assert.ok(!diagram.connections.some(([a,b])=>a===id+':1'||b===id+':1'));
  }
});
function harness(){
  let now=100000; const values=new Map();
  const flow={get:k=>values.get(k),set:(k,v)=>values.set(k,v)};
  const call=(file,msg={})=>new Function('msg','flow','Date',fs.readFileSync(path.join(root,'node-red/functions',file+'.js'),'utf8'))(msg,flow,{now:()=>now});
  return {flow,call,advance:ms=>now+=ms,now:()=>now};
}
function packet(overrides={}){return {session:'deadbeef',last_command_seq:0,rain_adc:1000,light_adc:1500,rain:false,dark:false,
  dht_valid:true,safe_to_open:true,temperature_c:30,humidity_pct:60,limit_covered:false,limit_open:false,
  estop:false,driver_fault:false,motor_output_enabled:false,motor_active:false,mode:'AUTO',motion:'IDLE',fault:'NONE',
  cover_request:'OPEN',cover_reason:'NORMAL',command_result:'ACCEPTED',last_command_result:'NONE',...overrides};}
function state(h,overrides={}){return h.call('normalize',{payload:packet(overrides)});}
function send(h,command,extra={}){return h.call('ha-command',{payload:{command,issued_at:h.now(),...extra}});}
test('normalized telemetry validates types/ranges and refuses retained/stale replay',()=>{
  const h=harness(); const out=h.call('normalize',{payload:JSON.stringify(packet({rain_adc:'2200',rain:'true'}))});
  assert.equal(out.payload.rain_adc,2200);assert.equal(out.payload.rain,true);
  for(const overrides of [{rain_adc:5000},{humidity_pct:101},{dark:'maybe'},{session:'wrong'},{mode:'RUN'},{safe_to_open:undefined}]){
    assert.equal(h.call('normalize',{payload:packet(overrides)}),null);
  }
  h.advance(500);assert.equal(h.call('normalize',{payload:packet(),retain:true}),null);
  assert.equal(h.flow.get('dryerState').receivedAt,100000);
});
test('75/85 percent humidity and invalid DHT produce the correct HA flags',()=>{
  const h=harness();
  let d=state(h,{humidity_pct:75}).payload;assert.equal(d.humidity_warning,true);assert.equal(d.humidity_danger,false);assert.equal(d.safe_to_open,false);
  d=state(h,{humidity_pct:85}).payload;assert.equal(d.humidity_danger,true);assert.equal(d.safe_to_open,false);
  d=state(h,{dht_valid:false,temperature_c:-999,humidity_pct:-999}).payload;
  assert.equal(d.temperature_c,null);assert.equal(d.humidity_pct,null);assert.equal(d.safe_to_open,false);
});

test('humidity advisory updates only the proposal; safety transitions stay distinct',()=>{
  const h=harness();
  let d=state(h,{humidity_pct:69.9}).payload;assert.equal(d.safety_status,'SAFE');assert.equal(d.cover_request,'OPEN');
  for(const humidity of [70,75,80]){
    d=state(h,{humidity_pct:humidity}).payload;
    assert.equal(d.cover_request,'CLOSE');assert.equal(d.cover_reason,'HUMIDITY_WARNING');
    assert.equal(d.safety_status,'WARNING');assert.equal(d.motion,'IDLE');assert.equal(d.mode,'AUTO');
  }
  d=state(h,{humidity_pct:80.1,cover_request:'CLOSE',cover_reason:'HUMIDITY_DANGER'}).payload;assert.equal(d.safety_status,'DANGER');
  d=state(h,{safe_to_open:false,open_wait_remaining_s:18}).payload;assert.equal(d.safety_status,'WAITING');
  d=state(h,{fault:'MOTION_TIMEOUT'}).payload;assert.equal(d.safety_status,'DANGER');
  d=state(h,{rain:true}).payload;assert.equal(d.safety_status,'DANGER');
});

test('HA bridge carries device countdown without estimating time for old firmware',()=>{
  const h=harness();
  assert.equal(state(h,{cover_request:'CLOSE',cover_reason:'WAITING_SAFE',open_wait_remaining_s:18}).payload.cover_reason,'WAITING_SAFE');
  assert.equal(state(h).payload.open_wait_remaining_s,null);
  for(const remaining of [-1,0,1,15,30]){
    assert.equal(state(h,{open_wait_remaining_s:remaining}).payload.open_wait_remaining_s,remaining);
    assert.equal(JSON.parse(h.call('ha-state')[0].payload).open_wait_remaining_s,remaining);
  }
  for(const remaining of [-2,31,1.5,'bad',null]){
    assert.equal(h.call('normalize',{payload:packet({open_wait_remaining_s:remaining})}),null);
  }
});
test('physical roof state comes only from limits, never requested movement',()=>{
  const h=harness();
  assert.equal(state(h,{cover_request:'CLOSE',motion:'CLOSING'}).payload.roof_position,'unknown');
  assert.equal(state(h,{limit_covered:true}).payload.roof_position,'closed');
  assert.equal(state(h,{limit_open:true}).payload.roof_position,'open');
  const d=state(h,{limit_covered:true,limit_open:true}).payload;
  assert.equal(d.roof_position,'FAULT');assert.equal(d.limit_fault,true);assert.equal(d.safe_to_open,false);
});
test('HA CLOSE uses existing firmware envelope; MANUAL is a stationary STOP',()=>{
  const h=harness();state(h);let [msg,ack]=send(h,'CLOSE');
  assert.match(msg.payload,/^deadbeef \d+ CLOSE$/);assert.equal(msg.retain,false);assert.equal(msg.qos,'0');
  assert.equal(JSON.parse(ack.payload).result,'PENDING');
  const sequence=h.flow.get('haPending').sequence;
  state(h,{last_command_seq:sequence,last_command_result:'ACCEPTED'});
  ack=h.call('ha-state')[1];assert.equal(JSON.parse(ack.payload).result,'ACCEPTED');
  h.advance(1100);[msg]=send(h,'MANUAL');assert.match(msg.payload,/ STOP$/);
});
test('reject retained, expired, future, malformed and offline requests',()=>{
  const h=harness();state(h);
  const cases=[{payload:{command:'OPEN',issued_at:h.now()},retain:true},
    {payload:{command:'OPEN',issued_at:h.now()-5001}},{payload:{command:'OPEN',issued_at:h.now()+3000}},
    {payload:{command:'OPEN'}},{payload:'not json'},{payload:{command:'REBOOT',issued_at:h.now()}}];
  for(const request of cases)assert.equal(h.call('ha-command',request)[0],null);
  h.advance(10000);assert.equal(send(h,'OPEN')[0],null);
});
test('rate limiting/busy checks never block STOP, and no movement retry after timeout',()=>{
  const h=harness();state(h);send(h,'OPEN');
  assert.equal(JSON.parse(send(h,'CLOSE')[1].payload).result,'REJECTED_RATE_LIMIT');
  assert.ok(send(h,'STOP')[0]);h.advance(1100);
  assert.equal(JSON.parse(send(h,'AUTO')[1].payload).result,'REJECTED_BUSY');
  h.advance(4000);const outputs=h.call('ha-watchdog');
  assert.equal(JSON.parse(outputs[2].payload).result,'TIMEOUT');assert.equal(h.flow.get('haPending'),null);
  assert.ok(outputs.every(m=>!m || m.topic!=='dryer/command'));
});
test('unsafe OPEN is forwarded only as a request, and ESP rejection is exposed',()=>{
  const h=harness();state(h,{rain:true,safe_to_open:false});const [msg]=send(h,'OPEN');assert.match(msg.payload,/ OPEN$/);
  const sequence=h.flow.get('haPending').sequence;
  state(h,{rain:true,safe_to_open:false,last_command_seq:sequence,last_command_result:'REJECTED_INTERLOCK_OR_COMMAND'});
  assert.equal(JSON.parse(h.call('ha-state')[1].payload).result,'REJECTED_INTERLOCK_OR_COMMAND');
});
test('offline after freshness timeout, new device session never replays an old command',()=>{
  const h=harness();state(h);send(h,'OPEN');h.advance(10000);
  assert.equal(h.call('ha-watchdog')[0].payload,'offline');
  state(h,{session:'1234abcd'});h.advance(1000);send(h,'AUTO');
  state(h,{session:'9876abcd'});assert.equal(JSON.parse(h.call('ha-state')[1].payload).result,'DEVICE_RESTARTED');
});
