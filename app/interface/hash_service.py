from abc import ABC, abstractmethod

class IHashService(ABC):
    """
    Interface trừu tượng quản lý băm và xác thực mật khẩu.
    """
    @abstractmethod
    def hash_password(self, password: str) -> str:
        """Băm mật khẩu dạng clear-text sang mật khẩu an toàn."""
        pass

    @abstractmethod
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Kiểm tra xem mật khẩu gốc có khớp với mật khẩu đã băm không."""
        pass
