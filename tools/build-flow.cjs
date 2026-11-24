const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, 'node-red', file), 'utf8');
const flow = [
  {id:'dryer-tab', type:'tab', label:'Agricultural dryer', disabled:false, info:'Local lab dashboard at /dryer. Commands are never retained.'},
  {id:'dryer-broker', type:'mqtt-broker', name:'Mosquitto (Docker)', broker:'mosquitto', port:'1883', clientid:'dryer-node-red', autoConnect:true, usetls:false, protocolVersion:'4', keepalive:'30', cleansession:true, autoUnsubscribe:true},
  {id:'telemetry-in', type:'mqtt in', z:'dryer-tab', name:'Telemetry', topic:'dryer/telemetry', qos:'0', datatype:'json', broker:'dryer-broker', x:140,y:80,wires:[['cache']]},
  {id:'cache', type:'function', z:'dryer-tab', name:'Cache fresh telemetry', func:read('functions/cache.js'), outputs:1, x:390,y:80,wires:[[]]},
  {id:'page-in', type:'http in', z:'dryer-tab', name:'Dashboard', url:'/dryer', method:'get', upload:false, x:140,y:160,wires:[['page']]},
  {id:'page', type:'template', z:'dryer-tab', name:'Dashboard HTML', field:'payload', fieldType:'msg', format:'html', syntax:'plain', template:read('dashboard.html'), output:'str', x:380,y:160,wires:[['html-headers']]},
  {id:'html-headers', type:'change', z:'dryer-tab', name:'HTML headers', rules:[{t:'set',p:'headers',pt:'msg',to:'{"Content-Type":"text/html; charset=utf-8","Cache-Control":"no-store"}',tot:'json'}], x:610,y:160,wires:[['http-out']]},
  {id:'state-in', type:'http in', z:'dryer-tab', name:'State API', url:'/dryer/state', method:'get', upload:false, x:140,y:240,wires:[['state']]},
  {id:'state', type:'function', z:'dryer-tab', name:'State freshness', func:read('functions/state.js'), outputs:1, x:390,y:240,wires:[['http-out']]},
  {id:'command-in', type:'http in', z:'dryer-tab', name:'Command API', url:'/dryer/command', method:'post', upload:false, x:140,y:320,wires:[['command']]},
  {id:'command', type:'function', z:'dryer-tab', name:'Validate and sequence command', func:read('functions/command.js'), outputs:2, x:420,y:320,wires:[['command-out'],['http-out']]},
  {id:'command-out', type:'mqtt out', z:'dryer-tab', name:'Non-retained command', topic:'dryer/command', qos:'1', retain:'false', broker:'dryer-broker', x:720,y:320,wires:[]},
  {id:'http-out', type:'http response', z:'dryer-tab', name:'HTTP response', statusCode:'', headers:{}, x:760,y:240,wires:[]}
];
const output = JSON.stringify(flow, null, 2) + '\n';
const haFlow = [
  {id:'dryer-ha-tab',type:'tab',label:'Dryer - Home Assistant bridge',disabled:false,info:'MQTT bridge for Home Assistant alongside the existing Node-RED dashboard.'},
  {id:'dryer-ha-broker',type:'mqtt-broker',name:'Existing Mosquitto - HA bridge',broker:'mosquitto',port:'1883',clientid:'dryer-ha-bridge',autoConnect:true,usetls:false,protocolVersion:'4',keepalive:'15',cleansession:true,autoUnsubscribe:true,
    willTopic:'dryer/ha/availability',willQos:'0',willPayload:'offline',willRetain:false,
    closeTopic:'dryer/ha/availability',closeQos:'0',closePayload:'offline',closeRetain:false},
  {id:'ha-telemetry',type:'mqtt in',z:'dryer-ha-tab',name:'Live firmware telemetry',topic:'dryer/telemetry',qos:'0',datatype:'json',broker:'dryer-ha-broker',x:130,y:80,wires:[['ha-normalize']]},
  {id:'ha-normalize',type:'function',z:'dryer-ha-tab',name:'Validate and normalize',func:read('functions/normalize.js'),outputs:1,x:370,y:80,wires:[['ha-state','ha-debug']]},
  {id:'ha-state',type:'function',z:'dryer-ha-tab',name:'HA state and device acknowledgement',func:read('functions/ha-state.js'),outputs:2,x:650,y:80,wires:[['ha-mqtt-out'],['ha-mqtt-out','ha-debug']]},
  {id:'ha-command-in',type:'mqtt in',z:'dryer-ha-tab',name:'Home Assistant command requests',topic:'dryer/ha/command',qos:'0',datatype:'json',broker:'dryer-ha-broker',x:160,y:180,wires:[['ha-command']]},
  {id:'ha-command',type:'function',z:'dryer-ha-tab',name:'TTL, replay, throttle, envelope',func:read('functions/ha-command.js'),outputs:2,x:490,y:180,wires:[['ha-mqtt-out'],['ha-mqtt-out','ha-debug']]},
  {id:'ha-timer',type:'inject',z:'dryer-ha-tab',name:'Freshness / command timeout',props:[],repeat:'2',crontab:'',once:true,onceDelay:'0.5',x:160,y:280,wires:[['ha-watchdog']]},
  {id:'ha-watchdog',type:'function',z:'dryer-ha-tab',name:'Offline after 10s, ACK timeout 5s',func:read('functions/ha-watchdog.js'),outputs:3,x:500,y:280,wires:[['ha-mqtt-out'],['ha-mqtt-out'],['ha-mqtt-out','ha-debug']]},
  {id:'ha-mqtt-out',type:'mqtt out',z:'dryer-ha-tab',name:'Non-retained state / commands',topic:'',qos:'0',retain:'false',broker:'dryer-ha-broker',x:950,y:180,wires:[]},
  {id:'ha-debug',type:'debug',z:'dryer-ha-tab',name:'Dryer HA telemetry / ACK',active:false,tosidebar:true,console:false,tostatus:false,complete:'payload',targetType:'msg',x:960,y:300,wires:[]}
];
for (const [filename, nodes] of [['flows.json',[...flow,...haFlow]],['home-assistant.flow.json',haFlow]]) {
  const target = path.join(root, 'node-red', filename);
  const content = JSON.stringify(nodes,null,2)+'\n';
  if (process.argv.includes('--check')) {
    if (fs.readFileSync(target,'utf8') !== content) throw Error(filename+' is out of date; run node tools/build-flow.cjs');
  } else fs.writeFileSync(target,content);
}
