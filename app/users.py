import datetime as dt
import json
from io import BytesIO

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for

from .auth import login_required
from .db import connect
from .protocols import REGISTRY
from .security import validate_csrf

users_bp = Blueprint("users", __name__)

def list_users():
    today = dt.date.today()
    with connect() as c:
        rows = c.execute("""
        SELECT u.*,
               GROUP_CONCAT(CASE WHEN p.enabled=1 THEN p.protocol END) AS protocols
        FROM users u
        LEFT JOIN user_protocols p ON p.user_id=u.id
        GROUP BY u.id
        ORDER BY u.id DESC
        """).fetchall()
        usage = {
            (r["user_id"], r["protocol"]): dict(r)
            for r in c.execute("SELECT * FROM protocol_usage").fetchall()
        }

    result = []
    for row in rows:
        item = dict(row)
        try:
            item["remaining_days"] = max(0, (dt.date.fromisoformat(item["expire_date"]) - today).days)
        except Exception:
            item["remaining_days"] = 0
        item["protocol_usage"] = {
            p: usage.get((item["id"], p), {})
            for p in (item.get("protocols") or "").split(",") if p
        }
        result.append(item)
    return result

def get_user(name):
    with connect() as c:
        row = c.execute("SELECT * FROM users WHERE username=?", (name,)).fetchone()
    return dict(row) if row else None

def protocol_meta(uid, protocol=None):
    with connect() as c:
        if protocol:
            row = c.execute(
                "SELECT * FROM user_protocols WHERE user_id=? AND protocol=? AND enabled=1",
                (uid, protocol),
            ).fetchone()
            rows = [row] if row else []
        else:
            rows = c.execute(
                "SELECT * FROM user_protocols WHERE user_id=? AND enabled=1",
                (uid,),
            ).fetchall()
    result = {}
    for row in rows:
        if not row:
            continue
        try:
            cfg = json.loads(row["config_json"] or "{}")
        except Exception:
            cfg = {}
        result[row["protocol"]] = {
            "identifier": row["identifier"],
            "config": cfg,
        }
    return result

@users_bp.get("/")
@login_required
def index():
    return render_template("index.html", users=list_users())

@users_bp.post("/users")
@login_required
def add():
    validate_csrf()
    created = []
    try:
        name = request.form["username"].strip()
        password = request.form["password"]
        limit = float(request.form["limit_gb"])
        days = int(request.form["days"])
        if get_user(name):
            raise ValueError("این نام کاربری قبلاً ثبت شده است.")

        protocols = list(dict.fromkeys(
            p for p in request.form.getlist("protocols") if p in {"ssh","ikev2"}
        )) or ["ssh"]

        expire = (dt.date.today() + dt.timedelta(days=days)).isoformat()
        user = {
            "username": name,
            "password": password,
            "limit_gb": limit,
            "used_gb": 0,
            "expire_date": expire,
            "status": "Active",
            "paused": 0,
            "initial_gb": limit,
            "initial_days": days,
        }

        metadata = {}
        for protocol in protocols:
            metadata[protocol] = REGISTRY[protocol].create(user)
            created.append(protocol)

        with connect() as c:
            cur = c.execute("""
            INSERT INTO users(username,password,limit_gb,expire_date,initial_gb,initial_days)
            VALUES(?,?,?,?,?,?)
            """, (name, password, limit, expire, limit, days))
            uid = cur.lastrowid
            for protocol in protocols:
                meta = metadata[protocol]
                c.execute("""
                INSERT INTO user_protocols(user_id,protocol,enabled,identifier,config_json)
                VALUES(?,?,1,?,?)
                """, (uid, protocol, meta.get("identifier"), json.dumps(meta.get("config") or {})))
                c.execute("""
                INSERT OR IGNORE INTO protocol_usage(user_id,protocol)
                VALUES(?,?)
                """, (uid, protocol))
            c.commit()

        flash("کاربر با موفقیت ساخته شد.", "success")
    except Exception as exc:
        for protocol in reversed(created):
            try:
                REGISTRY[protocol].delete({"username": request.form.get("username", "")})
            except Exception:
                pass
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("users.index"))

@users_bp.post("/users/<name>/edit")
@login_required
def edit(name):
    validate_csrf()
    user = get_user(name)
    if not user:
        return redirect(url_for("users.index"))
    try:
        password = request.form.get("password") or user["password"]
        limit = float(request.form.get("limit_gb", user["limit_gb"]))
        used = float(request.form.get("used_gb", user["used_gb"]))
        remaining = request.form.get("remaining_days")
        expire = (
            (dt.date.today() + dt.timedelta(days=int(remaining))).isoformat()
            if remaining not in (None, "")
            else user["expire_date"]
        )
        updated = {**user, "password": password, "limit_gb": limit, "used_gb": used, "expire_date": expire}
        metas = protocol_meta(user["id"])
        for protocol, meta in metas.items():
            REGISTRY[protocol].update(updated, meta)

        with connect() as c:
            c.execute("""
            UPDATE users SET password=?,limit_gb=?,used_gb=?,expire_date=?,updated_at=CURRENT_TIMESTAMP
            WHERE username=?
            """, (password, limit, used, expire, name))
            c.commit()
        flash("ویرایش ذخیره شد.", "success")
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("users.index"))

@users_bp.post("/users/<name>/<action>")
@login_required
def state(name, action):
    validate_csrf()
    user = get_user(name)
    try:
        if not user:
            raise ValueError("کاربر پیدا نشد.")
        metas = protocol_meta(user["id"])
        if action in ("pause", "resume"):
            for protocol, meta in metas.items():
                getattr(REGISTRY[protocol], action)(user, meta)
            paused = int(action == "pause")
            with connect() as c:
                c.execute(
                    "UPDATE users SET paused=?,status=?,updated_at=CURRENT_TIMESTAMP WHERE username=?",
                    (paused, "Paused" if paused else "Active", name),
                )
                c.commit()
        elif action == "delete":
            for protocol, meta in metas.items():
                REGISTRY[protocol].delete(user, meta)
            with connect() as c:
                c.execute("DELETE FROM users WHERE username=?", (name,))
                c.commit()
        flash("عملیات انجام شد.", "success")
    except Exception as exc:
        flash(f"خطا: {exc}", "error")
    return redirect(url_for("users.index"))

@users_bp.get("/users/<name>/config/<protocol>")
@login_required
def config(name, protocol):
    user = get_user(name)
    if not user or protocol not in REGISTRY:
        return ("Not found", 404)
    meta = protocol_meta(user["id"], protocol).get(protocol)
    if not meta:
        return ("Not enabled", 404)
    item = REGISTRY[protocol].client(user, meta)
    return send_file(
        BytesIO(item["content"].encode()),
        as_attachment=True,
        download_name=item["filename"],
        mimetype="text/plain",
    )

@users_bp.get("/users/<name>/config/ikev2-ca")
@login_required
def ike_ca(name):
    user = get_user(name)
    if not user or "ikev2" not in protocol_meta(user["id"]):
        return ("Not enabled", 404)
    path = "/etc/swanctl/x509ca/custom-panel-ca.crt"
    return send_file(path, as_attachment=True, download_name="custom-panel-ca.crt")

