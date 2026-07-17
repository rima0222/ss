import re

USERNAME = re.compile(r"^[a-z_][a-z0-9_-]{0,30}$")

def validate_username(value: str) -> str:
    value = value.strip()
    if not USERNAME.fullmatch(value):
        raise ValueError("نام کاربری باید با حرف کوچک شروع شود و فقط شامل حروف کوچک، عدد، _ یا - باشد.")
    return value

def validate_password(value: str) -> str:
    if len(value) < 4 or len(value) > 128:
        raise ValueError("رمز کاربر باید بین ۴ تا ۱۲۸ کاراکتر باشد.")
    if "\n" in value or ":" in value:
        raise ValueError("رمز نمی‌تواند شامل خط جدید یا : باشد.")
    return value

def as_int(value, minimum=None, maximum=None, label="مقدار"):
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} نامعتبر است.")
    if minimum is not None and number < minimum:
        raise ValueError(f"{label} نباید کمتر از {minimum} باشد.")
    if maximum is not None and number > maximum:
        raise ValueError(f"{label} نباید بیشتر از {maximum} باشد.")
    return number

def as_float(value, minimum=None, maximum=None, label="مقدار"):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} نامعتبر است.")
    if minimum is not None and number < minimum:
        raise ValueError(f"{label} نباید کمتر از {minimum} باشد.")
    if maximum is not None and number > maximum:
        raise ValueError(f"{label} نباید بیشتر از {maximum} باشد.")
    return number
