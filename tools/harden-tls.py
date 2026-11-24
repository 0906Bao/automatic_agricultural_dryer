"""Migrate the provisioned dryer stack to verified MQTT TLS. No secrets on stdout."""
import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import socket
import ssl
import sys
import urllib.request
import urllib.parse
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.pio/ha-tools'))
spec = importlib.util.spec_from_file_location('priority1', ROOT / 'tools/harden-priority1.py')
p1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p1)
LOCAL = p1.LOCAL


def admin_token():
    account = json.loads((LOCAL / 'credentials.json').read_text(encoding='utf-8'))['node_red']
    form = urllib.parse.urlencode({'client_id':'node-red-admin', 'grant_type':'password', 'scope':'*', **account}).encode()
    with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:1880/auth/token', data=form), timeout=15) as response:
        return json.load(response)['access_token']


def prepare():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
    if (LOCAL / 'tls-migration.json').exists():
        raise RuntimeError('TLS migration already prepared; refusing to replace its CA')
    token = admin_token()
    current = p1.node('/flows', token=token)
    backup = LOCAL / ('before-tls-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S'))
    backup.mkdir()
    (backup / 'flows.json').write_text(json.dumps(current), encoding='utf-8')
    (backup / 'node-red-data.tar').write_bytes(p1.run(['docker','exec','iot-node-red','tar','-C','/data','-cf','-','.']))
    for relative in ['docker-compose.yml','mosquitto/mosquitto.conf','include/secrets.local.h','.pio/build/wokwi/firmware.bin','.pio/build/wokwi/firmware.elf']:
        source = ROOT / relative
        if source.exists():
            target = backup / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
    pki = LOCAL / 'pki'
    server = pki / 'server'
    server.mkdir(parents=True)
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Agricultural Dryer Private CA')])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=3650))
          .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()),critical=False)
          .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False)
          .add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),critical=True)
          .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    dns = ['mosquitto','iot-mosquitto','localhost','host.wokwi.internal','host.docker.internal']
    ips = ['127.0.0.1','192.168.137.1','192.168.1.4']
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'mosquitto')]))
            .issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-timedelta(days=1)).not_valid_after(now+timedelta(days=397))
            .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()),critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),critical=False)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(n) for n in dns]+[x509.IPAddress(ipaddress.ip_address(n)) for n in ips]),critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False)
            .add_extension(x509.KeyUsage(True,False,True,False,False,False,False,False,False),critical=True)
            .sign(ca_key,hashes.SHA256()))
    private = lambda k:k.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    (pki/'ca.key').write_bytes(private(ca_key))
    (pki/'ca.crt').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (server/'server.key').write_bytes(private(key))
    (server/'server.crt').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    ca_text=(pki/'ca.crt').read_text(encoding='utf-8')
    (ROOT/'include/mqtt_ca.local.h').write_text('#pragma once\nstatic const char MQTT_CA_PEM[] = R"PEM('+ca_text+')PEM";\n#define MQTT_CA_CERT MQTT_CA_PEM\n',encoding='utf-8')
    path=ROOT/'include/secrets.local.h'
    source=path.read_text(encoding='utf-8')
    source,count=re.subn(r'^\s*#define\s+MQTT_PORT\b[^\r\n]*','#define MQTT_PORT 8883',source,flags=re.M)
    if not count:source+='\n#define MQTT_PORT 8883\n'
    path.write_text(source,encoding='utf-8')
    state={'backup':str(backup),'expires_at':cert.not_valid_after_utc.isoformat(),'ca_sha256':ca.fingerprint(hashes.SHA256()).hex()}
    (LOCAL/'tls-migration.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    print(json.dumps({'prepared':True,**state}))


def deploy_nodes():
    token=admin_token()
    current=p1.node('/flows',token=token)
    generated=json.loads((ROOT/'node-red/flows.json').read_text(encoding='utf-8'))
    managed={n['id']:n for n in generated}
    changed=[]
    for n in current['flows']:
        if n['type']=='mqtt-broker':
            if n['broker'] not in ['mosquitto','iot-mosquitto']:raise RuntimeError('Unrecognised MQTT broker')
            n.update(port='8883',usetls=True,verifyservercert=True,tls='dryer-mqtt-tls')
            changed.append(n['id'])
        elif n['type']=='function' and n['id'] in managed:
            n['func']=managed[n['id']]['func']
            changed.append(n['id'])
    ids={n['id'] for n in current['flows']}
    for ident in ['dryer-mqtt-tls','security-status-in','security-status-log']:
        if ident not in ids:current['flows'].append(managed[ident])
    p1.node('/flows',current,token)
    (LOCAL/'tls-expected-flows.json').write_text(json.dumps(current),encoding='utf-8')
    print(json.dumps({'runtime_updated':True,'existing_nodes':len(ids),'total_nodes':len(current['flows']),'updated_ids':changed}))


def complete_certificate_ids():
    """Complete identifiers on the initial certificates, preserving the same keys."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    pki=LOCAL/'pki'
    ca_key=serialization.load_pem_private_key((pki/'ca.key').read_bytes(),None)
    def complete(path,signing_key,issuer_key):
        old=x509.load_pem_x509_certificate(path.read_bytes())
        builder=(x509.CertificateBuilder().subject_name(old.subject).issuer_name(old.issuer).public_key(old.public_key())
                 .serial_number(old.serial_number).not_valid_before(old.not_valid_before_utc).not_valid_after(old.not_valid_after_utc))
        for extension in old.extensions:
            if not isinstance(extension.value,(x509.SubjectKeyIdentifier,x509.AuthorityKeyIdentifier)):
                builder=builder.add_extension(extension.value,extension.critical)
        builder=builder.add_extension(x509.SubjectKeyIdentifier.from_public_key(old.public_key()),False)
        builder=builder.add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(issuer_key),False)
        cert=builder.sign(signing_key,hashes.SHA256())
        path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        return cert
    ca=complete(pki/'ca.crt',ca_key,ca_key.public_key())
    complete(pki/'server/server.crt',ca_key,ca_key.public_key())
    text=(pki/'ca.crt').read_text(encoding='utf-8')
    (ROOT/'include/mqtt_ca.local.h').write_text('#pragma once\nstatic const char MQTT_CA_PEM[] = R"PEM('+text+')PEM";\n#define MQTT_CA_CERT MQTT_CA_PEM\n',encoding='utf-8')
    state=json.loads((LOCAL/'tls-migration.json').read_text(encoding='utf-8'))
    state['ca_sha256']=ca.fingerprint(hashes.SHA256()).hex()
    (LOCAL/'tls-migration.json').write_text(json.dumps(state,indent=2),encoding='utf-8')
    print(json.dumps({'certificate_identifiers_completed':True}))


def deploy_ha():
    access=p1.ha_access()
    account=json.loads((LOCAL/'credentials.json').read_text(encoding='utf-8'))
    flow=p1.ha(access,'/config/config_entries/flow',{'handler':'mqtt','entry_id':account['ha_entry_id']})
    (LOCAL/'tls-ha-schema.json').write_text(json.dumps(flow),encoding='utf-8')
    boundary='dryer-'+uuid.uuid4().hex
    certificate=(LOCAL/'pki/ca.crt').read_bytes()
    body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="dryer-ca.crt"\r\nContent-Type: application/x-x509-ca-cert\r\n\r\n'.encode()+certificate+f'\r\n--{boundary}--\r\n'.encode())
    req=urllib.request.Request(access['url']+'/api/file_upload',data=body,headers={'Authorization':'Bearer '+access['access_token'],'Content-Type':'multipart/form-data; boundary='+boundary})
    with urllib.request.urlopen(req,timeout=20) as response:file_id=json.load(response)['file_id']
    data={'broker':'192.168.137.1','port':8883,'protocol':'5','username':'dryer-homeassistant','password':account['mqtt']['dryer-homeassistant'],
          'other_settings':{'set_client_cert':False,'set_ca_cert':'custom','certificate':file_id,'tls_insecure':False,'transport':'tcp'}}
    result=p1.ha(access,'/config/config_entries/flow/'+flow['flow_id'],data)
    (LOCAL/'tls-ha-result.json').write_text(json.dumps(result),encoding='utf-8')
    if result['type']!='abort' or result.get('reason')!='reconfigure_successful':
        print(json.dumps({'type':result['type'],'step':result.get('step_id'),'errors':result.get('errors',{})}))
        raise RuntimeError('HA TLS reconfigure incomplete')
    print(json.dumps({'homeassistant_tls':True,'certificate_check':True}))


def verify():
    context=ssl.create_default_context(cafile=str(LOCAL/'pki/ca.crt'))
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    with socket.create_connection(('127.0.0.1',8883),timeout=5) as raw:
        with context.wrap_socket(raw,server_hostname='localhost') as secure:version=secure.version()
    for bad_context,hostname in [(context,'wrong-broker.invalid'),(ssl.create_default_context(),'localhost')]:
        try:
            with socket.create_connection(('127.0.0.1',8883),timeout=5) as raw:
                with bad_context.wrap_socket(raw,server_hostname=hostname):pass
        except ssl.SSLCertVerificationError:pass
        else:raise RuntimeError('Untrusted certificate or hostname was accepted')
    for port in [1883]:
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=2):pass
        except OSError:pass
        else:raise RuntimeError('Plaintext MQTT is still exposed')
    account=json.loads((LOCAL/'credentials.json').read_text(encoding='utf-8'))
    worker=(ROOT/'tools/verify-mqtt-security.cjs').read_text(encoding='utf-8')
    result=json.loads(p1.run(['docker','exec','-i','iot-node-red','node','-e',worker],json.dumps(account).encode()))
    actual=p1.node('/flows',token=admin_token())
    expected=json.loads((LOCAL/'tls-expected-flows.json').read_text(encoding='utf-8'))
    clean=lambda nodes:{n['id']:{k:v for k,v in n.items() if k!='credentials'} for n in nodes}
    if clean(actual['flows'])!=clean(expected['flows']):raise RuntimeError('Unexpected runtime flow changes')
    report={'tls_version':version,'wrong_ca_rejected':True,'wrong_hostname_rejected':True,'plaintext_port_closed':True,'mqtt':result,'runtime_nodes':len(actual['flows'])}
    (LOCAL/'tls-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


def verify_commands():
    account=json.loads((LOCAL/'credentials.json').read_text(encoding='utf-8'))
    worker=(ROOT/'tools/verify-command-security.cjs').read_text(encoding='utf-8')
    result=json.loads(p1.run(['docker','exec','-i','iot-node-red','node','-e',worker],json.dumps(account).encode()))
    # Create one failed login to verify that the enabled audit logger records it.
    data=urllib.parse.urlencode({'client_id':'node-red-admin','grant_type':'password','scope':'*','username':'dryer-admin','password':'incorrect-security-audit-test'}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:1880/auth/token',data=data),timeout=10):pass
    except urllib.error.HTTPError as error:
        if error.code not in [400,401,403]:raise
        result['invalid_admin_password_status']=error.code
    else:raise RuntimeError('Invalid Node-RED admin password accepted')
    (LOCAL/'sequence-verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['prepare','deploy_nodes','deploy_ha','verify','verify_commands','complete_certificate_ids'])
    args=parser.parse_args()
    try:globals()[args.action]()
    except Exception as error:
        print(str(error) if isinstance(error,RuntimeError) else type(error).__name__,file=sys.stderr)
        sys.exit(1)
