"""Isolated live MQTT -> Node-RED -> HA test, never the real dryer topics.

Uses a telemetry/ACK emulator, NOT real ESP32 sensors/motor. Adds only a
temporary namespaced Node-RED tab and HA package; removes those in finally.
"""
import argparse
import copy
import http.client
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/".pio/ha-tools"))
import paho.mqtt.client as mqtt
import yaml

parser=argparse.ArgumentParser()
parser.add_argument("--credentials",type=Path,default=Path(os.environ["LOCALAPPDATA"])/"AutomaticAgriculturalDryer/HAOS/access.json")
parser.add_argument("--vm",default="192.168.137.50")
parser.add_argument("--skip-restart",action="store_true",help="Do not restart a HA Core currently in use")
args=parser.parse_args();access=json.loads(args.credentials.read_text())
base=access["url"];namespace=str(int(time.time()));prefix="dryer_smoke_"+namespace
topic="dryertest/"+namespace+"/"
headers={"Authorization":"Bearer "+access["access_token"],"Content-Type":"application/json"}
ssh=["ssh","-i",str(ROOT/".local/haos-debug"),"-p","22222","-o","BatchMode=yes","-o","UserKnownHostsFile="+str(ROOT/".local/haos-known-hosts"),"root@"+args.vm]
scp=["scp","-O","-i",str(ROOT/".local/haos-debug"),"-P","22222","-o","BatchMode=yes","-o","UserKnownHostsFile="+str(ROOT/".local/haos-known-hosts")]

def request(url,data=None,extra=None):
    req=urllib.request.Request(url,data=json.dumps(data).encode() if data is not None else None,headers=extra or headers)
    with urllib.request.urlopen(req,timeout=45) as response:
        text=response.read().decode();return json.loads(text) if text else None
def api(path,data=None):return request(base+"/api"+path,data)
def node_get():return request("http://localhost:1880/flows",extra={"Node-RED-API-Version":"v2"})
def node_set(current,flows):return request("http://localhost:1880/flows",{"rev":current["rev"],"flows":flows},
    {"Node-RED-API-Version":"v2","Node-RED-Deployment-Type":"nodes","Content-Type":"application/json"})
def transform(value):
    if isinstance(value,dict):return {transform(k):transform(v) for k,v in value.items()}
    if isinstance(value,list):return [transform(v) for v in value]
    if isinstance(value,str):return value.replace("dryer_",prefix+"_").replace("dryer/",topic)
    return value
def remote(command):return subprocess.run(ssh+[command],check=True,capture_output=True,text=True).stdout
def reload():
    for service in ["mqtt/reload","template/reload","script/reload"]:api("/services/"+service,{})
def state(entity):
    try:return api("/states/"+entity)["state"]
    except urllib.error.HTTPError as error:
        if error.code==404:return None
        raise
def wait(entity,expected,timeout=15):
    deadline=time.monotonic()+timeout;last=None
    while time.monotonic()<deadline:
        try:last=state(entity)
        except (urllib.error.URLError,TimeoutError,ConnectionError,http.client.RemoteDisconnected):time.sleep(.5);continue
        if last==expected:return
        time.sleep(.25)
    raise AssertionError(f"{entity}: expected {expected}, got {last}")
def e(domain,key):return domain+"."+prefix+"_"+key

packet={"session":"deadbeef","last_command_seq":0,"rain_adc":1000,"light_adc":1500,"rain":False,"dark":False,
    "temperature_c":30,"humidity_pct":60,"dht_valid":True,"safe_to_open":True,"limit_covered":False,"limit_open":False,
    "estop":False,"driver_fault":False,"motor_output_enabled":False,"motor_active":False,"mode":"AUTO","motion":"IDLE",
    "fault":"NONE","cover_request":"OPEN","cover_reason":"NORMAL","command_result":"ACCEPTED","last_command_result":"NONE"}
lock=threading.RLock();stop=threading.Event();streaming=threading.Event();streaming.set()
commands=[];connected=threading.Event();fail_open=False;report=[]
client=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id="dryer-smoke-"+namespace)
def on_connect(client,userdata,flags,reason,props):
    if reason==0:client.subscribe(topic+"command");connected.set()
def on_message(client,userdata,msg):
    global fail_open
    if msg.topic!=topic+"command":return
    session,seq,cmd=msg.payload.decode().split()
    with lock:
        commands.append(cmd);packet["last_command_seq"]=int(seq)
        packet["last_command_result"]="REJECTED_INTERLOCK_OR_COMMAND" if cmd=="OPEN" and fail_open else "ACCEPTED"
def publish():
    while not stop.wait(.5):
        if streaming.is_set():
            with lock:payload=json.dumps(packet)
            client.publish(topic+"telemetry",payload,qos=0,retain=False)
def set_packet(**values):
    with lock:packet.update(values)
    time.sleep(.7)
def passed(name):report.append(name);print("PASS live:",name,flush=True)

source=json.loads((ROOT/"node-red/home-assistant.flow.json").read_text())
ids={node["id"]:"smoke-"+namespace+"-"+node["id"] for node in source}
def clone(value):
    if isinstance(value,dict):return {k:clone(v) for k,v in value.items()}
    if isinstance(value,list):return [clone(v) for v in value]
    if isinstance(value,str):return ids.get(value,value.replace("dryer/",topic))
    return value
nodes=clone(source)
for node in nodes:
    if node["type"]=="mqtt-broker":node["clientid"]="dryer-ha-smoke-"+namespace
    if node["type"]=="tab":node["label"]="TEMP isolated HA test "+namespace
package=transform(copy.deepcopy(runpy.run_path(str(ROOT/"tools/build-home-assistant.py"))["package"]))
package.pop("automation",None)
temp=ROOT/".local"/(prefix+".yaml");temp.write_text(yaml.safe_dump(package,allow_unicode=True,sort_keys=False),encoding="utf-8")
guest="/mnt/data/supervisor/homeassistant/packages/"+prefix+".yaml"
installed=False;tab_installed=False;success=False
try:
    subprocess.run(scp+[str(temp),"root@"+args.vm+":"+guest],check=True,capture_output=True)
    installed=True;reload()
    current=node_get();node_set(current,current["flows"]+nodes);tab_installed=True
    client.on_connect=on_connect;client.on_message=on_message
    client.connect("localhost",1883,15);client.loop_start()
    if not connected.wait(5):raise RuntimeError("Test MQTT client not connected")
    thread=threading.Thread(target=publish,daemon=True);thread.start()
    wait(e("sensor","temperature"),"30");passed("MQTT -> Node-RED -> HA temperature")
    wait(e("sensor","auto_status"),"Đang bật");wait(e("binary_sensor","auto_enabled"),"on")
    wait(e("sensor","mode_text"),"Tự động");passed("AUTO confirmed by telemetry is shown in Vietnamese")
    set_packet(mode="STOPPED");wait(e("sensor","auto_status"),"Đang tắt")
    api("/services/button/press",{"entity_id":e("button","auto")})
    wait(e("sensor","command_result"),"ACCEPTED")
    wait(e("sensor","auto_status"),"Đang tắt");wait(e("binary_sensor","auto_enabled"),"off")
    passed("AUTO button and ACK do not falsely enable automatic status")
    set_packet(mode="AUTO");wait(e("sensor","auto_status"),"Đang bật")
    set_packet(mode="MANUAL_CLOSE");wait(e("sensor","auto_status"),"Đang tắt")
    wait(e("sensor","mode_text"),"Thủ công: đóng bạt");passed("manual mode clearly disables automatic status")
    set_packet(temperature_c=36);wait(e("sensor","temperature"),"36");passed("temperature changes")
    set_packet(humidity_pct=75,safe_to_open=False);wait(e("binary_sensor","humidity_warning"),"on");passed("75% warning")
    set_packet(humidity_pct=85,cover_request="CLOSE",cover_reason="HUMIDITY_DANGER")
    wait(e("binary_sensor","humidity_danger"),"on");wait(e("sensor","cover_request"),"CLOSE");passed("85% danger and request displayed")
    set_packet(rain=True,rain_adc=2300,cover_reason="RAIN");wait(e("binary_sensor","rain"),"on");passed("rain status")
    set_packet(dark=True,light_adc=2300,cover_reason="DARK");wait(e("binary_sensor","dark"),"on");passed("dark status")
    set_packet(dht_valid=False,temperature_c=-999,humidity_pct=-999,cover_reason="DHT_ERROR")
    wait(e("sensor","temperature"),"unavailable");wait(e("binary_sensor","dht_valid"),"off");passed("invalid DHT hides old temperature")
    api("/services/button/press",{"entity_id":e("button","close")})
    deadline=time.monotonic()+5
    while "CLOSE" not in commands and time.monotonic()<deadline:time.sleep(.1)
    wait(e("sensor","command_result"),"ACCEPTED");assert "CLOSE" in commands;passed("HA CLOSE -> envelope -> emulated ACK")
    time.sleep(1.1);fail_open=True
    api("/services/cover/open_cover",{"entity_id":e("cover","roof")})
    wait(e("sensor","command_result"),"REJECTED_INTERLOCK_OR_COMMAND");passed("cover OPEN -> emulated rejection displayed")
    set_packet(limit_covered=True,limit_open=False);wait(e("cover","roof"),"closed");wait(e("sensor","roof_position"),"Đã đóng hoàn toàn");passed("closed limit confirms cover")
    set_packet(limit_covered=False,limit_open=True);wait(e("cover","roof"),"open");wait(e("sensor","roof_position"),"Đã mở hoàn toàn");passed("open limit confirms cover")
    set_packet(limit_covered=False,limit_open=False,cover_request="CLOSE");wait(e("cover","roof"),"unknown");wait(e("sensor","roof_position"),"Chưa chạm hành trình");passed("neither limit stays unknown")
    set_packet(limit_covered=True,limit_open=True);wait(e("cover","roof"),"unknown");wait(e("binary_sensor","limit_fault"),"on");wait(e("sensor","roof_position"),"Lỗi hai công tắc");passed("both limits fault without false position")
    streaming.clear();wait(e("binary_sensor","online"),"off",20)
    wait(e("sensor","auto_status"),"Chưa xác nhận");wait(e("binary_sensor","auto_enabled"),"unavailable")
    wait(e("sensor","rain_text"),"Mất kết nối");passed("stale telemetry offline and AUTO status is unconfirmed")
    set_packet(dht_valid=True,temperature_c=31,humidity_pct=60,rain=False,dark=False,limit_open=True,limit_covered=False)
    streaming.set();wait(e("binary_sensor","online"),"on");passed("telemetry recovers")
    # Actual HA Core restart, with the test producer/Node-RED left running.
    if not args.skip_restart:
        try:api("/services/homeassistant/restart",{})
        except (urllib.error.URLError,TimeoutError,ConnectionError,http.client.RemoteDisconnected):pass
        time.sleep(10)
        wait(e("sensor","temperature"),"31",60);passed("HA restart reconnects MQTT and resumes live states")
    success=True
finally:
    stop.set();client.disconnect();client.loop_stop()
    if tab_installed:
        current=node_get();node_set(current,[node for node in current["flows"] if node["id"] not in set(ids.values())])
    if installed:
        # This one file was created by this invocation; never remove other config.
        remote("rm -- '"+guest+"'")
        deadline=time.monotonic()+60
        while True:
            try:api("/");break
            except (urllib.error.URLError,TimeoutError,ConnectionError,http.client.RemoteDisconnected):
                if time.monotonic()>deadline:raise
                time.sleep(.5)
        reload()
        subprocess.run(["node",str(ROOT/"tools/ha-registry-cleanup.cjs"),prefix],check=True)
    (ROOT/".local/ha-runtime-test-result.json").write_text(json.dumps({"namespace":namespace,"success":success,"passed":report,
        "scope":"live HA/Node-RED/MQTT with isolated telemetry and ACK emulator, not ESP32/motor"},indent=2),encoding="utf-8")
print("Live checks passed:",len(report),"; temporary test nodes/package removed.")
