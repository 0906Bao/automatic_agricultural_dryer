const data = msg.payload;
if (msg.retain === true) return null;
if (!data || typeof data !== 'object' || Array.isArray(data) ||
    !/^[0-9a-f]{8}$/.test(data.session) ||
    !Number.isSafeInteger(data.last_command_seq) || data.last_command_seq < 0 || data.last_command_seq > 4294967295) return null;
flow.set('dryerState', { data, receivedAt: Date.now() });
return null;
