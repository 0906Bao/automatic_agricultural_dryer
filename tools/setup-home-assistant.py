"""Bootstrap only a NEW HA instance through its normal onboarding/REST APIs.

Passwords/tokens live outside Git in the user's local HAOS directory. No .storage
files are edited and an existing owner is never replaced/reset.
"""
import argparse
import getpass
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

parser=argparse.ArgumentParser()
parser.add_argument("--url",default="http://localhost:8123")
parser.add_argument("--broker",default="192.168.137.1")
parser.add_argument("--credentials",type=Path,default=Path(os.environ["LOCALAPPDATA"])/"AutomaticAgriculturalDryer/HAOS/access.json")
parser.add_argument("--mqtt-credentials",type=Path,default=Path(__file__).resolve().parents[1]/".local/security/credentials.json")
parser.add_argument("--mqtt-ca",type=Path,default=Path(__file__).resolve().parents[1]/".local/security/pki/ca.crt")
args=parser.parse_args();base=args.url.rstrip("/");client_id=base+"/"
access={}

def save():
    args.credentials.parent.mkdir(parents=True,exist_ok=True)
    args.credentials.write_text(json.dumps(access,indent=2),encoding="utf-8")
    if os.name=="nt":
        subprocess.run(["icacls",str(args.credentials),"/inheritance:r","/grant:r",getpass.getuser()+":(F)"],capture_output=True,check=True)
    else: args.credentials.chmod(0o600)

def call(path,data=None,auth=True,form=False):
    headers={}
    if auth: headers["Authorization"]="Bearer "+access["access_token"]
    if data is not None:
        headers["Content-Type"]="application/x-www-form-urlencoded" if form else "application/json"
        body=urllib.parse.urlencode(data).encode() if form else json.dumps(data).encode()
    else: body=None
    request=urllib.request.Request(base+path,data=body,headers=headers)
    try:
        with urllib.request.urlopen(request,timeout=45) as response:
            text=response.read().decode();return json.loads(text) if text else None
    except urllib.error.HTTPError as error:
        if path=="/api/onboarding" and error.code==404:
            return [{"step":"user","done":True}]
        # Never print a request containing credentials/tokens.
        raise RuntimeError(f"HA API {path}: HTTP {error.code}") from None

for attempt in range(10):
    try: status=call("/api/onboarding",auth=False);break
    except urllib.error.URLError:
        if attempt==9: raise
        time.sleep(1)
if args.credentials.exists():
    access=json.loads(args.credentials.read_text(encoding="utf-8"))
    response=call("/auth/token",{"grant_type":"refresh_token","refresh_token":access["refresh_token"],"client_id":client_id},auth=False,form=True)
    access["access_token"]=response["access_token"];save()
else:
    if any(step["step"]=="user" and step["done"] for step in status):
        raise SystemExit("Existing HA owner detected; use your own administrator login. No account was changed.")
    access={"url":base,"client_id":client_id,"username":"dryer-admin","password":secrets.token_urlsafe(24)}
    save() # preserve the password even if an interrupted bootstrap consumes its code
    response=call("/api/onboarding/users",{"name":"Dryer Administrator","username":access["username"],
        "password":access["password"],"client_id":client_id,"language":"vi"},auth=False)
    tokens=call("/auth/token",{"grant_type":"authorization_code","code":response["auth_code"],"client_id":client_id},auth=False,form=True)
    access.update({key:tokens[key] for key in ["access_token","refresh_token"]});save()

status=call("/api/onboarding",auth=False)
for step in ["core_config","analytics","integration"]:
    if any(item["step"]==step and not item["done"] for item in status):
        data={"client_id":client_id,"redirect_uri":base+"/"} if step=="integration" else {}
        call("/api/onboarding/"+step,data)
entries=call("/api/config/config_entries/entry")
if not any(entry["domain"]=="mqtt" for entry in entries):
    mqtt_credentials=json.loads(args.mqtt_credentials.read_text(encoding="utf-8"))["mqtt"]
    boundary="dryer-"+uuid.uuid4().hex
    body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="dryer-ca.crt"\r\nContent-Type: application/x-x509-ca-cert\r\n\r\n'.encode()
          +args.mqtt_ca.read_bytes()+f'\r\n--{boundary}--\r\n'.encode())
    upload=urllib.request.Request(base+"/api/file_upload",data=body,headers={"Authorization":"Bearer "+access["access_token"],"Content-Type":"multipart/form-data; boundary="+boundary})
    with urllib.request.urlopen(upload,timeout=20) as response:ca_file_id=json.load(response)["file_id"]
    flow=call("/api/config/config_entries/flow",{"handler":"mqtt","show_advanced_options":False})
    if flow.get("type")=="menu":
        flow=call("/api/config/config_entries/flow/"+flow["flow_id"],{"next_step_id":"broker"})
    print("MQTT setup step:",flow.get("step_id"))
    result=call("/api/config/config_entries/flow/"+flow["flow_id"],
        {"broker":args.broker,"port":8883,"protocol":"5",
         "username":"dryer-homeassistant","password":mqtt_credentials["dryer-homeassistant"],
         "other_settings":{"set_client_cert":False,"set_ca_cert":"custom","certificate":ca_file_id,"tls_insecure":False,"transport":"tcp"}})
    print("MQTT setup result:",result.get("type"),result.get("step_id"),result.get("errors",{}))
    if result.get("type")!="create_entry": raise SystemExit("MQTT setup requires another step; existing integrations preserved.")
print("HA onboarding complete. Username: dryer-admin; private credentials:",args.credentials)
states=call("/api/states")
print("Dryer entities loaded:",sum(".dryer_" in state["entity_id"] for state in states))
