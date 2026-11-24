const now = Date.now();
let request = msg.payload;
if (typeof request === 'string') { try { request=JSON.parse(request); } catch (_) { request=null; } }
const command = request && request.command;
const allowed = ['OPEN','CLOSE','STOP','AUTO','MANUAL','RESET'];
function reject(result) {
    return [null, {topic:'dryer/ha/command_result',payload:JSON.stringify({command:command || 'INVALID',result,completed_at:now}),qos:'0',retain:false}];
}
if (msg.retain === true) return reject('REJECTED_RETAINED');
if (!allowed.includes(command)) return reject('REJECTED_COMMAND');
if (!Number.isSafeInteger(request.issued_at) || now-request.issued_at > 5000 || now-request.issued_at < -2000) return reject('REJECTED_EXPIRED');
const state = flow.get('dryerState');
if (!state || now-state.receivedAt < 0 || now-state.receivedAt >= 10000) return reject('REJECTED_OFFLINE');
// ESP32 is still the final interlock. Forward OPEN so the device can confirm a
// rejection; this bridge never changes safe_to_open or bypasses its safety check.
const previous = flow.get('haLastSent');
if (command !== 'STOP' && previous !== undefined && now-previous < 1000) return reject('REJECTED_RATE_LIMIT');
const pending = flow.get('haPending');
if (command !== 'STOP' && pending) return reject('REJECTED_BUSY');
const sequence = Math.max(now, state.data.last_command_seq+1, (flow.get('haSequence') || 0)+1);
if (!Number.isSafeInteger(sequence)) return reject('REJECTED_SEQUENCE');
flow.set('haSequence', sequence); flow.set('haLastSent', now);
// MANUAL selects a safe, stationary manual state; subsequent OPEN/CLOSE moves it.
const action = command === 'MANUAL' ? 'STOP' : command;
const queued = {command,session:state.data.session,sequence,issued_at:request.issued_at,sent_at:now};
flow.set('haPending', queued);
return [{topic:'dryer/command',payload:`${state.data.session} ${sequence} ${action}`,qos:'0',retain:false},
    {topic:'dryer/ha/command_result',payload:JSON.stringify({...queued,result:'PENDING'}),qos:'0',retain:false}];
