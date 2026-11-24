const data = msg.payload;
if (!data || typeof data !== 'object' || Array.isArray(data) ||
    !/^[0-9a-f]{8}$/.test(data.session) ||
    !Number.isSafeInteger(data.last_command_seq) || data.last_command_seq < 0) return null;
flow.set('dryerState', { data, receivedAt: Date.now() });
return null;
