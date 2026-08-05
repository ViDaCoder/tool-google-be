import base64
import hashlib
from cryptography.fernet import Fernet

from app.config import settings
from app.interface.crypto_service import ICryptoService

class CryptoService(ICryptoService):
    """
    Dịch vụ mã hóa đối xứng thực thi ICryptoService sử dụng Cryptography Fernet (AES-128 in CBC).
    Khóa mã hóa được sinh ra đồng bộ từ SECRET_KEY của ứng dụng.
    """
    def __init__(self):
        # Fernet yêu cầu một khóa 32-byte được mã hóa base64 URL-safe.
        # Chúng ta dùng SHA-256 từ SECRET_KEY để luôn đảm bảo có 32-byte độc lập với độ dài SECRET_KEY gốc.
        key_bytes = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
        fernet_key = base64.urlsafe_b64encode(key_bytes)
        self.fernet = Fernet(fernet_key)

    def encrypt(self, plain_text: str) -> str:
        """Mã hóa chuỗi clear-text sang dạng mã hóa Fernet (string)."""
        if not plain_text:
            return ""
        return self.fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")

    def decrypt(self, encrypted_text: str) -> str:
        """Giải mã chuỗi mã hóa Fernet về dạng clear-text (string)."""
        if not encrypted_text:
            return ""
        return self.fernet.decrypt(encrypted_text.encode("utf-8")).decode("utf-8")
