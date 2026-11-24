"""Back up, check and reload only the project's HA package/dashboard over SSH."""
import json
import os
from pathlib import Path
import subprocess
import urllib.request
from datetime import datetime, timezone

ROOT=Path(__file__).resolve().parents[1]
access=json.loads((Path(os.environ["LOCALAPPDATA"])/"AutomaticAgriculturalDryer/HAOS/access.json").read_text())
vm="192.168.137.50"
options=["-i",str(ROOT/".local/haos-debug"),"-o","BatchMode=yes","-o","UserKnownHostsFile="+str(ROOT/".local/haos-known-hosts")]
ssh=["ssh","-p","22222",*options,"root@"+vm]
scp=["scp","-O","-P","22222",*options]
stamp=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
backup="/mnt/data/supervisor/share/dryer-config-backups/"+stamp
base="/mnt/data/supervisor/homeassistant/"
subprocess.run(ssh+["mkdir -p '"+backup+"'; cp '"+base+"packages/dryer.yaml' '"+backup+"/package.yaml'; cp '"+base+"dashboards/dryer.yaml' '"+backup+"/dashboard.yaml'"],check=True)
try:
    for rel in ["packages/dryer.yaml","dashboards/dryer.yaml"]:
        subprocess.run(scp+[str(ROOT/"home-assistant"/rel),"root@"+vm+":"+base+rel],check=True)
    subprocess.run(ssh+["ha core check"],check=True)
except Exception:
    subprocess.run(ssh+["cp '"+backup+"/package.yaml' '"+base+"packages/dryer.yaml'; cp '"+backup+"/dashboard.yaml' '"+base+"dashboards/dryer.yaml'"],check=True)
    raise
for service in ["mqtt/reload","template/reload"]:
    req=urllib.request.Request(access["url"]+"/api/services/"+service,data=b"{}",
        headers={"Authorization":"Bearer "+access["access_token"],"Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=45) as response:response.read()
print("Project config checked/reloaded without restarting Core. Backup:",backup)
