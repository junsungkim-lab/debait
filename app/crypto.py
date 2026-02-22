from cryptography.fernet import Fernet, InvalidToken
from .settings import settings

def _fernet() -> Fernet:
    return Fernet(settings.master_key.encode())

def encrypt_text(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()

def decrypt_text(cipher: str) -> str:
    try:
        return _fernet().decrypt(cipher.encode()).decode()
    except InvalidToken as e:
        raise ValueError("Invalid MASTER_KEY or ciphertext") from e
