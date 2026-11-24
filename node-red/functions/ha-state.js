const state = flow.get('dryerState');
if (!state) return null;
const pending = flow.get('haPending');
let ack = null;
if (pending && state.data.session !== pending.session) {
    ack = {...pending, result:'DEVICE_RESTARTED', completed_at:Date.now()};
} else if (pending && state.data.last_command_seq === pending.sequence) {
    ack = {...pending, result:state.data.last_command_result, completed_at:Date.now()};
} else if (pending && state.data.last_command_seq > pending.sequence) {
    ack = {...pending, result:'SUPERSEDED', completed_at:Date.now()};
}
if (ack) flow.set('haPending', null);
return [{topic:'dryer/ha/state', payload:JSON.stringify(state.data), qos:'0', retain:false},
    ack ? {topic:'dryer/ha/command_result', payload:JSON.stringify(ack), qos:'0', retain:false} : null];
