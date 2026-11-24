"""Read-only device/MQTT diagnostics. Never sends an actuator command."""
import json
import os
from pathlib import Path
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/".pio/ha-tools"))
import paho.mqtt.client as mqtt

credential_path=Path(os.environ["LOCALAPPDATA"])/"AutomaticAgriculturalDryer/HAOS/access.json"
access=json.loads(credential_path.read_text())
body=urllib.parse.urlencode({"grant_type":"refresh_token","refresh_token":access["refresh_token"],"client_id":access["client_id"]}).encode()
with urllib.request.urlopen(urllib.request.Request(access["url"]+"/auth/token",data=body),timeout=10) as response:
    access["access_token"]=json.load(response)["access_token"]
credential_path.write_text(json.dumps(access,indent=2),encoding="utf-8")
def api(path):
    req=urllib.request.Request(access["url"]+"/api"+path,headers={"Authorization":"Bearer "+access["access_token"]})
    with urllib.request.urlopen(req,timeout=15) as response:return json.load(response)
ids=["sensor.dryer_roof_position","binary_sensor.dryer_limit_closed","binary_sensor.dryer_limit_open",
     "binary_sensor.dryer_online","sensor.dryer_mode","sensor.dryer_motion","sensor.dryer_fault",
     "binary_sensor.dryer_motor_output_enabled"]
states={s["entity_id"]:{k:s.get(k) for k in ["state","last_changed","last_updated","last_reported"]}
    for s in api("/states") if s["entity_id"] in ids}
start=(datetime.now(timezone.utc)-timedelta(minutes=15)).isoformat()
query=urllib.parse.urlencode({"filter_entity_id":",".join(ids[:4]),"minimal_response":"","significant_changes_only":""})
history=api("/history/period/"+urllib.parse.quote(start,safe="")+"?"+query)
transitions=[[{k:s.get(k) for k in ["entity_id","state","last_changed"]} for s in group[-15:]] for group in history]
topics=["dryer/telemetry","dryer/availability","dryer/status"]
stats={};lock=threading.Lock();connected=threading.Event()
def on_connect(client,userdata,flags,reason,props):
    if reason==0:
        client.subscribe([(topic,0) for topic in topics]);connected.set()
def on_message(client,userdata,msg):
    now=time.monotonic()
    with lock:
        entry=stats.setdefault(msg.topic,{"count":0,"max_gap_s":0,"retained":0})
        if "last_at" in entry:entry["max_gap_s"]=max(entry["max_gap_s"],round(now-entry["last_at"],3))
        entry["last_at"]=now;entry["count"]+=1;entry["retained"]+=int(msg.retain)
        try:
            payload=json.loads(msg.payload)
            entry["last"]={k:payload.get(k) for k in ["session","limit_covered","limit_open","mode","motion","fault","motor_output_enabled"]}
        except (ValueError,TypeError):entry["last"]=msg.payload.decode(errors="replace")
client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id="dryer-readonly-diagnostic")
accounts=json.loads((ROOT/".local/security/credentials.json").read_text(encoding="utf-8"))["mqtt"]
client.username_pw_set("dryer-nodered",accounts["dryer-nodered"])
client.tls_set(ca_certs=str(ROOT/".local/security/pki/ca.crt"))
client.on_connect=on_connect;client.on_message=on_message
client.connect("localhost",8883,15);client.loop_start()
if not connected.wait(5):raise SystemExit("Diagnostic subscriber could not connect")
print("Observing MQTT for 35 seconds without issuing commands...",flush=True)
time.sleep(35);client.disconnect();client.loop_stop()
for entry in stats.values():entry.pop("last_at",None)
report={"states":states,"recent_history":transitions,"mqtt_35_seconds":stats}
(ROOT/".local/dryer-diagnostic.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report,indent=2))
