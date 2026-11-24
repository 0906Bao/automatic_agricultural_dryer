const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../home-assistant/www/dryer-status-card.js'),'utf8');
function card(states){
  const registered=new Map();
  class Element {setAttribute(){} }
  const context=vm.createContext({HTMLElement:Element,customElements:{get:k=>registered.get(k),define:(k,v)=>registered.set(k,v)},window:{}});
  vm.runInContext(source,context);
  const result=new (registered.get('dryer-status-card'))();
  result.hass={states:{'binary_sensor.dryer_online':{state:'on'},...states}};
  return result;
}
const row={entity:'sensor.dryer_rain_text',state_entity:'binary_sensor.dryer_rain',icon:'mdi:weather-rainy',colors:{on:'danger',off:'success'},state_icons:{on:'mdi:weather-pouring',off:'mdi:weather-sunny'}};
test('rain changes the status colour and icon without losing its Vietnamese description',()=>{
  const c=card({'binary_sensor.dryer_rain':{state:'off'},'sensor.dryer_rain_text':{state:'Không mưa'}});
  assert.equal(c.presentation(row).color,'success');assert.equal(c.presentation(row).icon,'mdi:weather-sunny');
  c._hass.states['binary_sensor.dryer_rain'].state='on';c._hass.states[row.entity].state='Có mưa';
  const view=c.presentation(row);assert.equal(view.color,'danger');assert.equal(view.icon,'mdi:weather-pouring');assert.equal(view.text,'Có mưa');
});
test('stale green values become neutral and unconfirmed when the device goes offline',()=>{
  const c=card({'binary_sensor.dryer_online':{state:'off'},'binary_sensor.dryer_rain':{state:'off'},'sensor.dryer_rain_text':{state:'Không mưa'}});
  assert.equal(c.presentation(row).color,'neutral');assert.match(c.presentation(row).text,/chưa xác nhận/);
  c._hass.states['binary_sensor.dryer_online'].state='on';c._hass.states[row.state_entity].state='unavailable';
  assert.equal(c.presentation(row).color,'neutral');assert.equal(c.presentation(row).text,'Chưa có dữ liệu');
});
test('faults are red, healthy safety signals green, and waiting conditions amber',()=>{
  const r={entity:'sensor.dryer_fault_text',state_entity:'sensor.dryer_fault',colors:{NONE:'success'},default_color:'danger'};
  const c=card({[r.entity]:{state:'Không có lỗi'},[r.state_entity]:{state:'NONE'}});
  assert.equal(c.presentation(r).color,'success');
  c._hass.states[r.state_entity].state='MOTION_TIMEOUT';assert.equal(c.presentation(r).color,'danger');
  const wait={entity:'sensor.dryer_cover_reason_text',state_entity:'sensor.dryer_cover_reason',colors:{NORMAL:'success',WAITING_SAFE:'warning'}};
  Object.assign(c._hass.states,{[wait.entity]:{state:'Đang chờ đủ 10 giây an toàn'},[wait.state_entity]:{state:'NORMAL'},'sensor.dryer_cover_request':{state:'CLOSE'}});
  assert.equal(c.presentation(wait).color,'warning');
});
test('duration is formatted as seconds and missing sensors are not shown as safe',()=>{
  const r={entity:'sensor.dryer_open_wait_remaining',state_entity:'binary_sensor.dryer_safe_to_open',colors:{on:'success',off:'warning'}};
  const c=card({[r.entity]:{state:'18.0',attributes:{unit_of_measurement:'s'}},[r.state_entity]:{state:'off'}});
  assert.equal(c.presentation(r).text,'18 s');assert.equal(c.presentation(r).color,'warning');
  delete c._hass.states[r.entity];assert.equal(c.presentation(r).color,'neutral');
});
