import time
import json
from pathlib import Path

Path("/run/custom-panel").mkdir(parents=True,exist_ok=True)

while True:
    data={
        "online_users":0,
        "traffic":{},
        "updated":int(time.time())
    }
    Path("/run/custom-panel/status.json").write_text(
        json.dumps(data)
    )
    time.sleep(2)
