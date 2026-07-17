from flask import Blueprint, jsonify

from ..ipc import request as manager_request
from ..settings import settings
from .common import login_required

api_bp = Blueprint("api", __name__, url_prefix="/api")

@api_bp.get("/stats")
@login_required
def stats():
    data = manager_request(
        settings.manager_socket,
        {"method": "stats", "params": {}},
        timeout=10,
    )
    return jsonify(data)

@api_bp.get("/health")
def health():
    try:
        result = manager_request(
            settings.manager_socket,
            {"method": "health", "params": {}},
            timeout=3,
        )
        return jsonify({"panel": "ok", "manager": result})
    except Exception as exc:
        return jsonify({"panel": "ok", "manager": "down", "error": str(exc)}), 503
