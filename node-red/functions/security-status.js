const reason = typeof msg.payload === 'string' ? msg.payload : '';
if (!/^REJECTED_[A-Z_]{1,60}$/.test(reason)) return null;
const previous = flow.get('dryerLastRejectionLog');
const now = Date.now();
if (!previous || reason !== previous.reason || now - previous.at >= 5000) {
    node.warn(JSON.stringify({event:'device_command_rejected',reason}));
    flow.set('dryerLastRejectionLog',{reason,at:now});
}
return null;
