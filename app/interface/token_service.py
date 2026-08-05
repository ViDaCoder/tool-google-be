from abc import ABC, abstractmethod
from datetime import timedelta

class ITokenService(ABC):
    """
    Interface trừu tượng quản lý cấp phát và xác thực JWT token.
    """
    @abstractmethod
    def create_access_token(self, data: dict, expires_delta: timedelta | None = None) -> str:
        """Tạo mới JWT Access Token chứa payload thông tin."""
        pass

    @abstractmethod
    def decode_access_token(self, token: str) -> dict | None:
        """Giải mã và xác thực JWT token."""
        pass
