// Runs inside the existing Node-RED container. Credentials arrive only on stdin.
// No valid actuator commands are published.
const mqtt = require('mqtt');
const assert = require('node:assert/strict');
let input = '';
process.stdin.on('data', chunk => input += chunk);
process.stdin.on('end', async () => {
  const credentials = JSON.parse(input);
  const clients = [];
  function connect(username, password, denied = false) {
    return new Promise((resolve, reject) => {
      const c = mqtt.connect('mqtts://mosquitto:8883', {
        ca:require('node:fs').readFileSync('/run/dryer/ca.crt'),rejectUnauthorized:true,minVersion:'TLSv1.2',
        protocolVersion: 5, username, password, reconnectPeriod: 0,
        connectTimeout: 4000, clientId: 'security-check-' + require('node:crypto').randomUUID()
      });
      clients.push(c);
      c.once('connect', () => denied ? reject(Error('Unauthorised connection accepted')) : resolve(c));
      c.once('error', error => {
        if (denied && [134, 135].includes(error.code)) { c.end(true); resolve(null); }
        else reject(Error('MQTT authentication check failed'));
      });
    });
  }
  const subscribe = (client, topic) => new Promise((resolve, reject) => client.subscribe(topic, {qos: 0}, error => error ? reject(error) : resolve()));
  const publish = (client, topic, payload, denied = false) => new Promise((resolve, reject) => {
    client.publish(topic, payload, {qos: 1, retain: false}, (error, packet) => {
      if (denied) {
        if (packet?.reasonCode === 135 || /not authorized/i.test(error?.message || '')) resolve();
        else reject(Error('Expected publish permission denial'));
      } else if (error) reject(Error('Allowed publish failed'));
      else resolve();
    });
  });
  const counts = {telemetry: 0, haState: 0, allowedStatus: 0, forbiddenStatus: 0};
  try {
    await connect(undefined, undefined, true);
    await connect('dryer-esp', 'incorrect-security-test-password', true);
    const esp = await connect('dryer-esp', credentials.mqtt['dryer-esp']);
    const nr = await connect('dryer-nodered', credentials.mqtt['dryer-nodered']);
    const ha = await connect('dryer-homeassistant', credentials.mqtt['dryer-homeassistant']);
    const marker = 'SECURITY_CHECK_' + Date.now();
    nr.on('message', (topic, payload) => {
      if (topic === 'dryer/telemetry') counts.telemetry++;
      if (topic === 'dryer/status' && payload.toString() === marker) counts.allowedStatus++;
    });
    ha.on('message', (topic, payload) => {
      if (topic === 'dryer/ha/state') counts.haState++;
      if (topic === 'dryer/status' && payload.toString() === marker) counts.forbiddenStatus++;
    });
    await subscribe(nr, ['dryer/telemetry', 'dryer/status']);
    // Read ACLs may filter delivery rather than deny the SUBSCRIBE itself.
    await subscribe(ha, ['dryer/ha/state', 'dryer/status']);
    await publish(esp, 'dryer/status', marker);
    await publish(nr, 'dryer/telemetry', '{}', true);
    await publish(ha, 'dryer/telemetry', '{}', true);
    await publish(esp, 'dryer/ha/state', '{}', true);
    await new Promise(resolve => setTimeout(resolve, 4000));
    assert.equal(counts.allowedStatus, 1);
    assert.equal(counts.forbiddenStatus, 0);
    assert.ok(counts.telemetry > 0, 'Live ESP telemetry missing');
    assert.ok(counts.haState > 0, 'Home Assistant bridge state missing');
    console.log(JSON.stringify({anonymousRejected: true, badPasswordRejected: true,
      accountsAccepted: 3, crossRolePublishesRejected: 3, readAclEnforced: true, liveMessages: counts}));
  } catch (error) {
    console.error('MQTT security verification failed: ' + error.message);
    process.exitCode = 1;
  } finally {
    clients.forEach(client => client.end(true));
  }
});
