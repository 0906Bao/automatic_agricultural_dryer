"""Build a local CONFIG ISO for a new HAOS VM (public SSH key + static NAT IP)."""
import argparse
import ipaddress
import io
from pathlib import Path
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/".pio/ha-tools"))
import pycdlib

parser=argparse.ArgumentParser()
parser.add_argument("--address",required=True)
parser.add_argument("--gateway",required=True)
args=parser.parse_args()
address=ipaddress.IPv4Interface(args.address)
gateway=ipaddress.IPv4Address(args.gateway)
if not address.ip.is_private or gateway not in address.network:
    raise SystemExit("Use a private VM address and gateway in the same network")
local=ROOT/".local";local.mkdir(exist_ok=True)
key=local/"haos-debug"
if not key.exists():
    subprocess.run(["ssh-keygen","-q","-t","ed25519","-N","","-f",str(key)],check=True)
network=f"""[connection]
id=Dryer HAOS NAT
uuid={uuid.uuid4()}
type=ethernet
autoconnect=true
autoconnect-priority=100
[ipv4]
method=manual
address1={address},{gateway}
dns={gateway};1.1.1.1;
[ipv6]
method=auto
"""
iso=pycdlib.PyCdlib();iso.new(interchange_level=3,joliet=3,vol_ident="CONFIG")
iso.add_directory(iso_path="/NETWORK",joliet_path="/network")
files=[("/AUTHORIZED_KEYS.;1","/authorized_keys",key.with_suffix(".pub").read_bytes()),
       ("/NETWORK/DEFAULT.;1","/network/default",network.encode("ascii"))]
for iso_path,joliet_path,data in files:
    iso.add_fp(io.BytesIO(data),len(data),iso_path=iso_path,joliet_path=joliet_path)
target=local/"haos-config.iso";iso.write(str(target));iso.close()
print(f"CONFIG ISO: {target}; guest address: {address.ip}; private key stays local")
