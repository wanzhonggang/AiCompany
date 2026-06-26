"""
Security utilities for encryption/decryption of sensitive data.
"""
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64
from .config import settings


def get_encryption_key() -> bytes:
    """Get or generate encryption key from environment."""
    if settings.encryption_key:
        return settings.encryption_key.encode()
    
    # Generate a key from a passphrase if ENCRYPTION_KEY not set
    passphrase = settings.encryption_passphrase
    salt = settings.encryption_salt.encode()
    
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=480000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode()))
    return key


_fernet: Fernet | None = None


def get_fernet() -> Fernet:
    """Get or create Fernet instance."""
    global _fernet
    if _fernet is None:
        key = get_encryption_key()
        _fernet = Fernet(key)
    return _fernet


def encrypt_data(data: str) -> str:
    """Encrypt string data."""
    fernet = get_fernet()
    return fernet.encrypt(data.encode()).decode()


def decrypt_data(encrypted_data: str) -> str:
    """Decrypt encrypted string data."""
    fernet = get_fernet()
    return fernet.decrypt(encrypted_data.encode()).decode()
