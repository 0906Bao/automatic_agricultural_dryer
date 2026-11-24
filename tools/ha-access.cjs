// TCP forwarding preserves Home Assistant HTTP/WebSocket without proxy headers.
const net=require('node:net');
const address=process.argv[2];
const port=Number(process.argv[3] || 80);
function privateIPv4(ip){return /^127\./.test(ip)||/^10\./.test(ip)||/^192\.168\./.test(ip)||/^172\.(1[6-9]|2\d|3[01])\./.test(ip);}
if(net.isIP(address)!==4 || !privateIPv4(address)) throw Error('Target must be a private IPv4 VM address');
if(!Number.isInteger(port)||port<1||port>65535)throw Error('Invalid target port');
const server=net.createServer(client=>{
  const remote=client.remoteAddress.replace(/^::ffff:/,'');
  if(!privateIPv4(remote)){client.destroy();return;}
  const upstream=net.connect({host:address,port});
  client.setKeepAlive(true,30000);upstream.setKeepAlive(true,30000);
  upstream.setTimeout(10000,()=>upstream.destroy());
  upstream.on('connect',()=>{upstream.setTimeout(0);client.pipe(upstream);upstream.pipe(client);});
  upstream.on('error',()=>client.destroy());client.on('error',()=>upstream.destroy());
  client.on('close',()=>upstream.destroy());upstream.on('close',()=>client.destroy());
});
server.on('error',error=>{console.error(error.message);process.exitCode=1;});
server.listen(8123,'0.0.0.0',()=>console.log(`Home Assistant: localhost:8123 -> ${address}:${port}; private LAN clients only`));
for(const signal of ['SIGINT','SIGTERM'])process.on(signal,()=>server.close());
