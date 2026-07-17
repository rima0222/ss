import argparse
import json
import secrets
import time

from cryptography.fernet import Fernet
from werkzeug.security import generate_password_hash

from .db import initialize, transaction
from .ipc import request
from .settings import settings

def init_admin(username, password):
    initialize(settings.db_path)
    with transaction(settings.db_path, immediate=True) as conn:
        conn.execute(
            """
            INSERT INTO admins(id,username,password_hash,session_version,updated_at)
            VALUES(1,?,?,1,?)
            ON CONFLICT(id) DO UPDATE SET
                username=excluded.username,
                password_hash=excluded.password_hash,
                session_version=admins.session_version+1,
                updated_at=excluded.updated_at
            """,
            (username, generate_password_hash(password), int(time.time())),
        )

def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init")
    init.add_argument("--admin-user", default="admin")
    init.add_argument("--admin-password", required=True)

    reset = sub.add_parser("reset-admin")
    reset.add_argument("--username", default="admin")
    reset.add_argument("--password", required=True)

    health = sub.add_parser("health")

    args = parser.parse_args()
    if args.command in {"init", "reset-admin"}:
        init_admin(args.admin_user if args.command == "init" else args.username, args.admin_password)
        print("OK")
    elif args.command == "health":
        print(json.dumps(request(
            settings.manager_socket,
            {"method": "health", "params": {}},
            timeout=5,
        )))

if __name__ == "__main__":
    main()
