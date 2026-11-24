const allowed = ['STOP', 'AUTO', 'OPEN', 'CLOSE', 'RESET'];
const command = msg.payload && msg.payload.command;
const state = flow.get('dryerState');
const age = state ? Date.now() - state.receivedAt : Infinity;
msg.headers = { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' };
if (!allowed.includes(command)) {
    msg.statusCode = 400; msg.payload = { error: 'Unknown command' }; return [null, msg];
}
if (!state || age < 0 || age >= 10000) {
    msg.statusCode = 409; msg.payload = { error: 'No fresh telemetry; use physical emergency stop' };
    return [null, msg];
}
const sequence = Math.max(Date.now(), state.data.last_command_seq + 1, (flow.get('dryerSeq') || 0) + 1);
if (!Number.isSafeInteger(sequence)) {
    msg.statusCode = 409; msg.payload = { error: 'Sequence exhausted; reboot device' }; return [null, msg];
}
flow.set('dryerSeq', sequence);
const outbound = { topic: 'dryer/command', payload: `${state.data.session} ${sequence} ${command}`,
    qos: '1', retain: false };
msg.statusCode = 202;
msg.payload = { queued: command, sequence, session: state.data.session };
return [outbound, msg];
