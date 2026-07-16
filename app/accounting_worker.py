import json, os, time
from pathlib import Path
from app.config import Config
from app.db import init_db, connect
from app.live import wireguard_stats, openvpn_stats

STATE=Path('/etc/custom-panel/runtime/accounting-state.json')
INTERVAL=15

def load_state():
    try: return json.loads(STATE.read_text())
    except Exception: return {}

def save_state(state):
    STATE.parent.mkdir(parents=True,exist_ok=True)
    tmp=STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state,separators=(',',':')))
    os.replace(tmp,STATE)

def counters():
    data={}
    for name,stat in wireguard_stats(Config.WG_INTERFACE).items():
        data.setdefault(name,{})['wireguard']=int(stat.get('rx_bytes',0))+int(stat.get('tx_bytes',0))
    for name,stat in openvpn_stats().items():
        data.setdefault(name,{})['openvpn']=int(stat.get('rx_bytes',0))+int(stat.get('tx_bytes',0))
    return data

def tick(state):
    current=counters(); deltas={}
    for user,protocols in current.items():
        for protocol,value in protocols.items():
            key=f'{user}:{protocol}'; previous=int(state.get(key,value))
            if value>=previous: deltas[user]=deltas.get(user,0)+(value-previous)
            state[key]=value
    if deltas:
        with connect() as c:
            c.executemany('UPDATE users SET used_gb=used_gb+?, updated_at=CURRENT_TIMESTAMP WHERE username=? AND paused=0',[(b/(1024**3),u) for u,b in deltas.items() if b>0])
            c.commit()
    save_state(state)
    return state

def main():
    init_db(Config.DB_PATH); state=load_state()
    while True:
        try: state=tick(state)
        except Exception: pass
        time.sleep(INTERVAL)

if __name__=='__main__': main()
