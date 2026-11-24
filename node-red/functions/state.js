const state = flow.get('dryerState');
const age = state ? Date.now() - state.receivedAt : Infinity;
msg.headers = { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' };
msg.payload = { online: age >= 0 && age < 10000, age_ms: Number.isFinite(age) ? age : null,
    telemetry: state ? state.data : null };
return msg;
