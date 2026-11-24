// Accept live packets only. Replayed retained telemetry cannot reset freshness.
if (msg.retain === true) return null;
let d = msg.payload;
if (typeof d === 'string') { try { d = JSON.parse(d); } catch (_) { return null; } }
if (!d || typeof d !== 'object' || Array.isArray(d)) return null;
const out = {};
const number = (v, min, max, integer = false) => {
    if (typeof v !== 'number' && (typeof v !== 'string' || !v.trim())) return null;
    const n = Number(v);
    return Number.isFinite(n) && n >= min && n <= max && (!integer || Number.isInteger(n)) ? n : null;
};
const bool = v => v === true || v === 1 || v === 'true' || v === '1' ? true :
    v === false || v === 0 || v === 'false' || v === '0' ? false : null;
if (typeof d.session !== 'string' || !/^[0-9a-f]{8}$/.test(d.session)) return null;
out.session = d.session;
for (const key of ['rain_adc', 'light_adc']) {
    out[key] = number(d[key], 0, 4095, true); if (out[key] === null) return null;
}
out.last_command_seq = number(d.last_command_seq, 0, Number.MAX_SAFE_INTEGER, true);
if (out.last_command_seq === null) return null;
for (const key of ['rain', 'dark', 'dht_valid', 'safe_to_open', 'limit_covered', 'limit_open',
    'estop', 'driver_fault', 'motor_output_enabled', 'motor_active']) {
    out[key] = bool(d[key]); if (out[key] === null) return null;
}
if (out.dht_valid) {
    out.temperature_c = number(d.temperature_c, -40, 80);
    out.humidity_pct = number(d.humidity_pct, 0, 100);
    if (out.temperature_c === null || out.humidity_pct === null) return null;
} else { out.temperature_c = null; out.humidity_pct = null; }
out.humidity_warning = out.dht_valid && out.humidity_pct >= 70;
out.humidity_danger = out.dht_valid && out.humidity_pct > 80;
const enums = {
    mode: ['STOPPED','AUTO','MANUAL_OPEN','MANUAL_CLOSE'],
    motion: ['IDLE','OPENING','CLOSING','REVERSAL_WAIT','FAULT'],
    fault: ['NONE','ESTOP','BOTH_LIMITS','MOTION_TIMEOUT','DRIVER_FAULT'],
    cover_request: ['OPEN','CLOSE'],
    cover_reason: ['NORMAL','RAIN','DARK','DHT_ERROR','HUMIDITY_WARNING','HUMIDITY_DANGER']
};
for (const [key, values] of Object.entries(enums)) {
    if (!values.includes(d[key])) return null; out[key] = d[key];
}
for (const key of ['command_result','last_command_result']) {
    if (typeof d[key] !== 'string' || !/^[A-Z_]{1,64}$/.test(d[key])) return null;
    out[key] = d[key];
}
out.limit_fault = out.limit_open && out.limit_covered;
// Never infer physical position or movement from a request/output alone.
out.roof_position = out.limit_fault ? 'FAULT' : out.limit_covered ? 'closed' :
    out.limit_open ? 'open' : 'unknown';
out.safe_to_open = out.safe_to_open && !out.rain && !out.dark && out.dht_valid &&
    out.humidity_pct < 70 && !out.limit_fault && !out.estop && !out.driver_fault && out.fault === 'NONE';
msg.payload = out;
flow.set('dryerState', {data:out, receivedAt:Date.now()});
return msg;
