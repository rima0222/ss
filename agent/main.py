import time,json
from pathlib import Path

Path('/run/custom-panel').mkdir(parents=True,exist_ok=True)

while True:
    Path('/run/custom-panel/status.json').write_text(
        json.dumps({'online':0,'traffic':0})
    )
    time.sleep(5)
