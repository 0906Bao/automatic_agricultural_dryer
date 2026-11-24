// Remove only registry entries created by a single isolated runtime test.
const fs=require('node:fs'),path=require('node:path');
const prefix=process.argv[2];
if(!/^dryer_smoke_\d+$/.test(prefix))throw Error('Only isolated smoke-test prefixes are allowed');
const access=JSON.parse(fs.readFileSync(path.join(process.env.LOCALAPPDATA,'AutomaticAgriculturalDryer/HAOS/access.json'),'utf8'));
const ws=new WebSocket(access.url.replace(/^http/,'ws')+'/api/websocket');
let id=1,pending=0,count=0;
const timer=setTimeout(()=>{console.error('Registry cleanup timed out');process.exitCode=1;ws.close();},20000);
ws.addEventListener('message',event=>{
  const message=JSON.parse(event.data);
  if(message.type==='auth_required')ws.send(JSON.stringify({type:'auth',access_token:access.access_token}));
  else if(message.type==='auth_ok')ws.send(JSON.stringify({id:id++,type:'config/entity_registry/list'}));
  else if(message.type==='auth_invalid'){console.error('Registry cleanup authentication failed');process.exitCode=1;ws.close();}
  else if(message.type==='result'){
    if(!message.success){console.error('Registry API failed');process.exitCode=1;ws.close();return;}
    if(message.id===1){
      const targets=message.result.filter(entry=>entry.entity_id.split('.')[1].startsWith(prefix+'_'));
      pending=targets.length;count=pending;
      for(const entry of targets)ws.send(JSON.stringify({id:id++,type:'config/entity_registry/remove',entity_id:entry.entity_id}));
      if(!pending)ws.close();
    }else if(--pending===0)ws.close();
  }
});
ws.addEventListener('close',()=>{clearTimeout(timer);console.log('Removed isolated test registry entries:',count);});
ws.addEventListener('error',()=>{console.error('Registry WebSocket connection failed');process.exitCode=1;ws.close();});
