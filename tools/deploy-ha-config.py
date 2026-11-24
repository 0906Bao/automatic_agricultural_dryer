"""Back up, check and reload only the project's HA package/dashboard over SSH."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
access=json.loads((Path(os.environ["LOCALAPPDATA"])/"AutomaticAgriculturalDryer/HAOS/access.json").read_text())
refresh=urllib.parse.urlencode({"grant_type":"refresh_token","refresh_token":access["refresh_token"],"client_id":access["client_id"]}).encode()
with urllib.request.urlopen(urllib.request.Request(access["url"]+"/auth/token",data=refresh),timeout=15) as response:
    access["access_token"]=json.load(response)["access_token"]
vm="192.168.137.50"
options=["-i",str(ROOT/".local/haos-debug"),"-o","BatchMode=yes","-o","UserKnownHostsFile="+str(ROOT/".local/haos-known-hosts")]
ssh=["ssh","-p","22222",*options,"root@"+vm]
scp=["scp","-O","-P","22222",*options]
stamp=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
backup="/mnt/data/supervisor/share/dryer-config-backups/"+stamp
base="/mnt/data/supervisor/homeassistant/"
subprocess.run(ssh+["mkdir -p '"+backup+"'; cp '"+base+"packages/dryer.yaml' '"+backup+"/package.yaml'; cp '"+base+"dashboards/dryer.yaml' '"+backup+"/dashboard.yaml'"],check=True)
try:
    subprocess.run(ssh+["mkdir -p '"+base+"www'"],check=True)
    subprocess.run(scp+[str(ROOT/"home-assistant/www/dryer-status-card.js"),"root@"+vm+":"+base+"www/dryer-status-card.js"],check=True)
    for rel in ["packages/dryer.yaml","dashboards/dryer.yaml"]:
        subprocess.run(scp+[str(ROOT/"home-assistant"/rel),"root@"+vm+":"+base+rel],check=True)
    subprocess.run(ssh+["ha core check"],check=True)
except Exception:
    subprocess.run(ssh+["cp '"+backup+"/package.yaml' '"+base+"packages/dryer.yaml'; cp '"+backup+"/dashboard.yaml' '"+base+"dashboards/dryer.yaml'"],check=True)
    raise
for service in ["mqtt/reload","template/reload","automation/reload"]:
    req=urllib.request.Request(access["url"]+"/api/services/"+service,data=b"{}",
        headers={"Authorization":"Bearer "+access["access_token"],"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=45) as response:response.read()
subprocess.run(["node",str(ROOT/"tools/register-ha-dashboard-resource.cjs")],check=True)
print("Project config checked/reloaded without restarting Core. Backup:",backup)
