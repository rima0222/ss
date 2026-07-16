from .db import connect

RANGES = {
    "openssh": (20000, 24999),
    "dropbear": (25000, 29999),
    "ws": (30000, 34999),
    "tls": (35000, 39999),
}

def allocate(column, transport):
    start, end = RANGES[transport]
    with connect() as c:
        used = {int(row[column]) for row in c.execute(
            f"SELECT {column} FROM users WHERE {column} IS NOT NULL"
        )}
    for port in range(start, end + 1):
        if port not in used:
            return port
    raise RuntimeError(f"ظرفیت پورت‌های {transport} تکمیل است.")
