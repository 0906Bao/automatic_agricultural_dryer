// Preserve existing runtime settings and the volume's credential encryption key.
// Missing provisioned authentication is a startup error, never an auth bypass.
const settings = require('/data/settings.js');
const auth = require('/run/dryer/node-red-auth.json');
for (const field of ['adminUser', 'adminHash', 'httpUser', 'httpHash']) {
  if (typeof auth[field] !== 'string' || !auth[field]) throw Error('Missing authentication field: ' + field);
}
if (![auth.adminHash, auth.httpHash].every(hash => /^\$2[aby]\$\d\d\$/.test(hash))) {
  throw Error('Authentication passwords must be bcrypt hashes');
}
module.exports = {
  ...settings,
  logging: {...settings.logging, console: {...settings.logging?.console, level:'info', metrics:false, audit:true}},
  adminAuth: {
    type: 'credentials',
    sessionExpiryTime: 3600,
    users: [{username: auth.adminUser, password: auth.adminHash, permissions: '*'}]
  },
  httpNodeAuth: {user: auth.httpUser, pass: auth.httpHash}
};
