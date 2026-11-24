const now = Date.now(), state = flow.get('dryerState');
const live = state && now-state.receivedAt >= 0 && now-state.receivedAt < 10000;
const pending = flow.get('haPending');
let timeout = null;
if (pending && now-pending.sent_at >= 5000) {
    timeout={topic:'dryer/ha/command_result',payload:JSON.stringify({...pending,result:'TIMEOUT',completed_at:now}),qos:'0',retain:false};
    flow.set('haPending',null); // never retry a movement command automatically
}
return [{topic:'dryer/ha/availability',payload:live ? 'online' : 'offline',qos:'0',retain:false},
    {topic:'dryer/ha/heartbeat',payload:live ? 'online' : 'offline',qos:'0',retain:false}, timeout];
