from cryptography.fernet import Fernet
from .settings import settings

def _cipher():
    if not settings.data_key:
        raise RuntimeError("CP_DATA_KEY is not configured")
    return Fernet(settings.data_key.encode())

def encrypt_text(value: str) -> str:
    return _cipher().encrypt(value.encode()).decode()

def decrypt_text(value: str) -> str:
    return _cipher().decrypt(value.encode()).decode()
