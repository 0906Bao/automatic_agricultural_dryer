// Read credentials on stdin; the only accepted actuator action tested is STOP.
const mqtt=require('mqtt'),fs=require('node:fs'),assert=require('node:assert/strict');
let input='';process.stdin.on('data',b=>input+=b);
process.stdin.on('end',async()=>{
  const credentials=JSON.parse(input);
  const client=mqtt.connect('mqtts://mosquitto:8883',{protocolVersion:5,username:'dryer-nodered',password:credentials.mqtt['dryer-nodered'],
    ca:fs.readFileSync('/run/dryer/ca.crt'),rejectUnauthorized:true,minVersion:'TLSv1.2',reconnectPeriod:0,connectTimeout:5000});
  let data=null;const rejections=[];
  client.on('message',(topic,bytes)=>{
    if(topic==='dryer/telemetry'){try{data=JSON.parse(bytes)}catch{}}
    if(topic==='dryer/status'&&bytes.toString().startsWith('REJECTED_'))rejections.push(bytes.toString());
  });
  const wait=async(predicate)=>{const start=Date.now();while(!predicate()){if(Date.now()-start>8000)throw Error('Device acknowledgement timed out');await new Promise(r=>setTimeout(r,100));}};
  const publish=text=>new Promise((resolve,reject)=>client.publish('dryer/command',text,{qos:1,retain:false},e=>e?reject(e):resolve()));
  try{
    await new Promise((resolve,reject)=>{client.once('connect',resolve);client.once('error',reject)});
    await new Promise((resolve,reject)=>client.subscribe(['dryer/telemetry','dryer/status'],e=>e?reject(e):resolve()));
    await wait(()=>data);
    assert.equal(data.motor_active,false,'Run the stationary STOP check only while motor is idle');
    const session=data.session,baseline=data.last_command_seq;
    await publish(`${session} 4294967295 STOP`);
    await wait(()=>rejections.length>0);
    await new Promise(r=>setTimeout(r,1300));
    assert.equal(data.last_command_seq,baseline,'Large sequence mutated the counter');
    await publish(`${session} ${baseline+1} STOP`);
    await wait(()=>data.last_command_seq===baseline+1&&data.last_command_result==='ACCEPTED');
    assert.equal(data.motor_active,false);
    const rejected=rejections.length;
    await publish(`${session} ${baseline+1} STOP`);
    await wait(()=>rejections.length>rejected);
    assert.equal(data.last_command_seq,baseline+1);
    console.log(JSON.stringify({largeJumpRejected:true,nextStopAccepted:true,duplicateRejected:true,motorRemainedIdle:true}));
  }catch(error){console.error('Sequence security check failed: '+error.message);process.exitCode=1;}
  finally{client.end(true);}
});
