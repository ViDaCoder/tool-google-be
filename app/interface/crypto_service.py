from abc import ABC, abstractmethod

class ICryptoService(ABC):
    """
    Interface trừu tượng phục vụ mã hóa và giải mã dữ liệu đối xứng (symmetric encryption).
    """
    @abstractmethod
    def encrypt(self, plain_text: str) -> str:
        """Mã hóa văn bản thuần túy sang dạng chuỗi mã hóa."""
        pass

    @abstractmethod
    def decrypt(self, encrypted_text: str) -> str:
        """Giải mã chuỗi mã hóa về văn bản gốc ban đầu."""
        pass
