"""Local security migration. Never prints passwords, tokens or flow contents."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local/security'
ACCESS = Path(os.environ['LOCALAPPDATA']) / 'AutomaticAgriculturalDryer/HAOS/access.json'


def run(args, data=None):
    result = subprocess.run(args, cwd=ROOT, input=data, capture_output=True)
    if result.returncode:
        # Child output can contain credentials. Keep it out of the terminal.
        raise RuntimeError(f'{args[0]} failed (exit {result.returncode})')
    return result.stdout


def request(url, data=None, headers=None, method=None):
    body = None if data is None else json.dumps(data).encode()
    h = {'Content-Type': 'application/json', **(headers or {})}
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read()
            return json.loads(body) if body else None
    except urllib.error.HTTPError as error:
        if LOCAL.exists():
            (LOCAL / 'last-http-error.txt').write_bytes(error.read())
        raise RuntimeError('HTTP request rejected: ' + str(error.code)) from None


def ha_access():
    access = json.loads(ACCESS.read_text(encoding='utf-8'))
    form = urllib.parse.urlencode({'grant_type': 'refresh_token', 'refresh_token': access['refresh_token'], 'client_id': access['client_id']}).encode()
    req = urllib.request.Request(access['url'] + '/auth/token', data=form)
    with urllib.request.urlopen(req, timeout=15) as response:
        access['access_token'] = json.load(response)['access_token']
    return access


def ha(access, path, data=None):
    return request(access['url'] + '/api' + path, data, {'Authorization': 'Bearer ' + access['access_token']})


def node(path, data=None, token=None):
    headers = {'Node-RED-API-Version': 'v2'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    if data is not None:
        headers['Node-RED-Deployment-Type'] = 'nodes'
    return request('http://127.0.0.1:1880' + path, data, headers)


def prepare():
    LOCAL.mkdir(parents=True, exist_ok=True)
    # Restrict inheritance before creating any credentials or backups.
    run(['icacls', str(LOCAL), '/inheritance:r', '/grant:r', os.environ['USERNAME'] + ':(OI)(CI)F'])
    credentials_path = LOCAL / 'credentials.json'
    if credentials_path.exists():
        raise RuntimeError('Credentials already prepared; refusing to rotate silently')
    access = ha_access()
    entries = ha(access, '/config/config_entries/entry')
    mqtt = [entry for entry in entries if entry['domain'] == 'mqtt']
    if len(mqtt) != 1:
        raise RuntimeError('Expected one existing MQTT integration')
    current = node('/flows')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    backup = LOCAL / ('before-' + stamp)
    backup.mkdir()
    (backup / 'flows.json').write_text(json.dumps(current), encoding='utf-8')
    (backup / 'node-red-data.tar').write_bytes(run(['docker', 'exec', 'iot-node-red', 'tar', '-C', '/data', '-cf', '-', '.']))
    for file in ['include/secrets.local.h', 'docker-compose.yml', 'compose.mqtt-secure.yml', 'mosquitto/mosquitto.conf']:
        source = ROOT / file
        if source.exists():
            target = backup / file
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    credentials = {'mqtt': {user: secrets.token_urlsafe(32) for user in ['dryer-esp', 'dryer-nodered', 'dryer-homeassistant']},
                   'node_red': {'username': 'dryer-admin', 'password': secrets.token_urlsafe(32)},
                   'dashboard': {'username': 'dryer-operator', 'password': secrets.token_urlsafe(32)},
                   'ha_entry_id': mqtt[0]['entry_id'], 'backup': str(backup)}
    credentials_path.write_text(json.dumps(credentials, indent=2), encoding='utf-8')
    hash_code = "const bcrypt=require('bcryptjs');let b='';process.stdin.on('data',x=>b+=x);process.stdin.on('end',()=>{const d=JSON.parse(b);console.log(JSON.stringify({adminUser:d.node_red.username,adminHash:bcrypt.hashSync(d.node_red.password,12),httpUser:d.dashboard.username,httpHash:bcrypt.hashSync(d.dashboard.password,12)}))});"
    auth = run(['docker', 'exec', '-i', 'iot-node-red', 'node', '-e', hash_code], json.dumps(credentials).encode())
    (LOCAL / 'node-red-auth.json').write_bytes(auth)
    # Feed plaintext over stdin, never in command arguments or shell history.
    password_code = 'umask 077; cat > /tmp/dryer-security-passwords; mosquitto_passwd -U /tmp/dryer-security-passwords >/dev/null 2>&1 && cat /tmp/dryer-security-passwords; result=$?; rm -f /tmp/dryer-security-passwords; exit "$result"'
    lines = ''.join(user + ':' + password + '\n' for user, password in credentials['mqtt'].items())
    hashed = run(['docker', 'exec', '-i', 'iot-mosquitto', 'sh', '-c', password_code], lines.encode())
    (LOCAL / 'passwords').write_bytes(hashed)
    path = ROOT / 'include/secrets.local.h'
    contents = path.read_text(encoding='utf-8')
    for key, value in [('MQTT_USER', 'dryer-esp'), ('MQTT_PASSWORD', credentials['mqtt']['dryer-esp'])]:
        definition = '#define ' + key + ' ' + json.dumps(value)
        contents, count = re.subn(r'^\s*#define\s+' + key + r'\b[^\r\n]*', lambda _: definition, contents, flags=re.M)
        if not count:
            contents += '\n' + definition + '\n'
    path.write_text(contents, encoding='utf-8')
    print(json.dumps({'prepared': True, 'backup': str(backup), 'mqtt_accounts': list(credentials['mqtt']),
                      'node_red_brokers': [n['id'] for n in current['flows'] if n['type'] == 'mqtt-broker'],
                      'ha_entry_state': mqtt[0].get('state')}))


def preflight():
    access = ha_access()
    entries = ha(access, '/config/config_entries/entry')
    states = ha(access, '/states')
    print(json.dumps({'mqtt_entries': [{'entry_id': e['entry_id'], 'state': e['state']} for e in entries if e['domain'] == 'mqtt'],
                      'safety_states': {s['entity_id']: s['state'] for s in states if s['entity_id'] in ['sensor.dryer_motion', 'binary_sensor.dryer_motor_active', 'binary_sensor.dryer_motor_output_enabled']}}))


def ha_schema():
    credentials = json.loads((LOCAL / 'credentials.json').read_text())
    access = ha_access()
    result = ha(access, '/config/config_entries/flow', {'handler': 'mqtt', 'entry_id': credentials['ha_entry_id']})
    (LOCAL / 'ha-reconfigure.json').write_text(json.dumps(result), encoding='utf-8')
    # Schema defaults may contain credentials: only print field names.
    print(json.dumps({'type': result['type'], 'step_id': result.get('step_id'),
                      'fields': [field.get('name') for field in result.get('data_schema', [])]}))


def node_credentials():
    credentials = json.loads((LOCAL / 'credentials.json').read_text())
    current = node('/flows')
    brokers = [n for n in current['flows'] if n['type'] == 'mqtt-broker']
    if not brokers:
        raise RuntimeError('No MQTT brokers found')
    for broker in brokers:
        if broker.get('broker') not in ['mosquitto', 'iot-mosquitto']:
            print(json.dumps({'unexpected_broker': {'id': broker['id'], 'host': broker.get('broker'), 'port': broker.get('port')}}))
            raise RuntimeError('Unexpected broker; refusing to overwrite another system account')
        broker['credentials'] = {'user': 'dryer-nodered', 'password': credentials['mqtt']['dryer-nodered']}
    result = node('/flows', current)
    print(json.dumps({'node_red_mqtt_accounts_updated': len(brokers), 'revision_updated': bool(result.get('rev'))}))


def ha_credentials():
    credentials = json.loads((LOCAL / 'credentials.json').read_text())
    access = ha_access()
    result = json.loads((LOCAL / 'ha-reconfigure.json').read_text())
    fields = result['data_schema']
    data = {}
    for field in fields:
        name = field.get('name')
        if name in ['broker', 'port', 'protocol', 'other_settings']:
            if 'suggested_value' in field.get('description', {}):
                data[name] = field['description']['suggested_value']
            elif 'default' in field:
                data[name] = field['default']
            elif name == 'other_settings':
                data[name] = {}
                for nested in field.get('schema', []):
                    if 'suggested_value' in nested.get('description', {}):
                        data[name][nested['name']] = nested['description']['suggested_value']
                    elif 'default' in nested:
                        data[name][nested['name']] = nested['default']
    data.update(username='dryer-homeassistant', password=credentials['mqtt']['dryer-homeassistant'])
    result = ha(access, '/config/config_entries/flow/' + result['flow_id'], data)
    (LOCAL / 'ha-reconfigure-result.json').write_text(json.dumps(result), encoding='utf-8')
    print(json.dumps({'type': result['type'], 'reason': result.get('reason'), 'errors': result.get('errors', {})}))
    if result['type'] != 'abort' or result.get('reason') != 'reconfigure_successful':
        raise RuntimeError('MQTT reconfiguration did not complete')


def verify():
    if (LOCAL / 'tls-migration.json').exists():
        print(run([sys.executable, str(ROOT / 'tools/harden-tls.py'), 'verify']).decode('utf-8').strip())
        return
    credentials = json.loads((LOCAL / 'credentials.json').read_text())
    try:
        node('/flows')
    except RuntimeError as error:
        if str(error) != 'HTTP request rejected: 401':
            raise
    else:
        raise RuntimeError('Anonymous Node-RED admin access is still enabled')
    form = urllib.parse.urlencode({'client_id': 'node-red-admin', 'grant_type': 'password', 'scope': '*',
                                  'username': credentials['node_red']['username'], 'password': credentials['node_red']['password']}).encode()
    req = urllib.request.Request('http://127.0.0.1:1880/auth/token', data=form)
    with urllib.request.urlopen(req, timeout=10) as response:
        token = json.load(response)['access_token']
    current = node('/flows', token=token)
    before = json.loads((Path(credentials['backup']) / 'flows.json').read_text())
    clean = lambda nodes: {n['id']: {k: v for k, v in n.items() if k != 'credentials'} for n in nodes}
    if clean(current['flows']) != clean(before['flows']):
        raise RuntimeError('Runtime flow contents changed unexpectedly')
    worker = (ROOT / 'tools/verify-mqtt-security.cjs').read_text(encoding='utf-8')
    mqtt = json.loads(run(['docker', 'exec', '-i', 'iot-node-red', 'node', '-e', worker], json.dumps(credentials).encode()))
    bindings = {}
    for name in ['iot-node-red', 'iot-mosquitto']:
        bindings[name] = json.loads(run(['docker', 'inspect', name, '--format', '{{json .HostConfig.PortBindings}}']))
    if {b['HostIp'] for b in bindings['iot-node-red']['1880/tcp']} != {'127.0.0.1'}:
        raise RuntimeError('Node-RED binding is not restricted to localhost')
    if {b['HostIp'] for b in bindings['iot-mosquitto']['1883/tcp']} != {'127.0.0.1', '192.168.137.1'}:
        raise RuntimeError('MQTT exposed on unexpected host interfaces')
    result = {'node_red_anonymous_status': 401, 'node_red_admin_login': True,
              'existing_flow_nodes_preserved': len(current['flows']), 'mqtt': mqtt, 'port_bindings': bindings}
    (LOCAL / 'verification.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['preflight', 'prepare', 'ha_schema', 'node_credentials', 'ha_credentials', 'verify'])
    args = parser.parse_args()
    try:
        globals()[args.action]()
    except Exception as error:
        detail = str(error) if isinstance(error, RuntimeError) else type(error).__name__
        print(f'{detail}: security migration stopped; no secrets printed', file=sys.stderr)
        sys.exit(1)
