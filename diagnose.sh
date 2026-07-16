#!/usr/bin/env bash
set -u
APP=/etc/custom-panel
echo "=== Files ==="
find "$APP" -maxdepth 2 -type f | sort || true
echo "=== Identities ==="
id custompanel || true
echo "=== Permissions ==="
namei -l "$APP" || true
ls -ld "$APP" "$APP/data" /run/custom-panel || true
echo "=== Services ==="
for s in ssh custom-panel-sshd custom-panel-helper custom-panel-proxy custom-panel-accounting custom-panel; do
  systemctl status "$s" --no-pager -l || true
done
echo "=== Logs ==="
for s in custom-panel-helper custom-panel-proxy custom-panel-accounting custom-panel; do
  journalctl -u "$s" -n 100 --no-pager || true
done
echo "=== Ports ==="
ss -lntp || true


echo "=== SQLite write check ==="
if [[ -f "$APP/.env" ]]; then
  ENV_ARGS=()
  while IFS='=' read -r key value; do
    [[ -z "$key" || "$key" == \#* ]] && continue
    ENV_ARGS+=("$key=$value")
  done < "$APP/.env"

  runuser -u custompanel -- env PYTHONPATH="$APP" "${ENV_ARGS[@]}" \
    "$APP/venv/bin/python" - <<'PY' || true
from app.config import Config
from app.db import init_db, connect
init_db(Config.DB_PATH)
with connect() as conn:
    conn.execute("CREATE TABLE IF NOT EXISTS diagnose_write_test(id INTEGER PRIMARY KEY)")
    conn.execute("INSERT OR REPLACE INTO diagnose_write_test(id) VALUES(1)")
    conn.commit()
    conn.execute("DROP TABLE diagnose_write_test")
    conn.commit()
print("SQLite writable: YES")
PY
fi


echo "=== Live accounting ==="
ls -lah /run/custom-panel/live.json 2>/dev/null || true
cat /run/custom-panel/live.json 2>/dev/null || true
echo
echo "=== Database counters ==="
sqlite3 /etc/custom-panel/data/panel.db \
  "SELECT username,rx_bytes,tx_bytes,online_tcp,online_ws FROM users;" 2>/dev/null || true


echo "=== Gateway validation ==="
echo "Managed users must use assigned ports, never port 22."
ss -lnt | grep -E '(:22 |127\.0\.0\.1:2222|:5000|:2[0-9]{4})' || true
echo "=== Live snapshot freshness ==="
python3 - <<'PY' || true
import json, time
p="/run/custom-panel/live.json"
d=json.load(open(p))
print("age_seconds:", int(time.time())-int(d.get("updated_at",0)))
print(json.dumps(d, indent=2))
PY


echo "=== Active gateway sessions ==="
python3 - <<'PY' || true
import json
p="/run/custom-panel/live.json"
d=json.load(open(p))
print("snapshot_updated_at:", d.get("updated_at"))
print("session_count:", d.get("session_count"))
for username, info in d.get("users", {}).items():
    print(username, info)
PY

echo "=== Persistent traffic ==="
sqlite3 /etc/custom-panel/data/panel.db "
SELECT
 username,
 printf('%.2f MB',(rx_bytes+tx_bytes)/1048576.0) AS used,
 printf('%.2f GB',limit_bytes/1073741824.0) AS quota,
 remaining_days,
 status
FROM users
ORDER BY id;
" 2>/dev/null || true
