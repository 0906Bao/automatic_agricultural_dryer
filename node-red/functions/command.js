const allowed = ['STOP', 'AUTO', 'OPEN', 'CLOSE', 'RESET'];
const command = msg.payload && msg.payload.command;
const state = flow.get('dryerState');
const age = state ? Date.now() - state.receivedAt : Infinity;
msg.headers = { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' };
function audit(reason) {
    if (typeof node !== 'undefined') node.warn(JSON.stringify({event:'command_rejected',source:'http',reason,
        command:allowed.includes(command) ? command : 'INVALID'}));
}
if (!allowed.includes(command)) {
    audit('INVALID_COMMAND');
    msg.statusCode = 400; msg.payload = { error: 'Unknown command' }; return [null, msg];
}
if (!state || age < 0 || age >= 10000) {
    audit('OFFLINE');
    msg.statusCode = 409; msg.payload = { error: 'No fresh telemetry; use physical emergency stop' };
    return [null, msg];
}
const acknowledged = state.data.last_command_seq;
const reserved = flow.get('dryerCommandSequence');
const base = reserved && reserved.session === state.data.session && reserved.value <= acknowledged + 63 ?
    Math.max(acknowledged, reserved.value) : acknowledged;
const sequence = base + 1;
if (!Number.isSafeInteger(acknowledged) || acknowledged < 0 || sequence > 4294967295) {
    audit('INVALID_SEQUENCE');
    msg.statusCode = 409; msg.payload = { error: 'Waiting for a valid device session' }; return [null, msg];
}
flow.set('dryerCommandSequence', {session:state.data.session, value:sequence});
const outbound = { topic: 'dryer/command', payload: `${state.data.session} ${sequence} ${command}`,
    qos: '1', retain: false };
msg.statusCode = 202;
msg.payload = { queued: command, sequence, session: state.data.session };
return [outbound, msg];
