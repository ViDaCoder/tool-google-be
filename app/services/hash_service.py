from passlib.context import CryptContext
from app.interface.hash_service import IHashService

class HashService(IHashService):
    """
    Dịch vụ băm mật khẩu thực thi từ IHashService bằng passlib/bcrypt.
    """
    def __init__(self):
        self.pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

    def hash_password(self, password: str) -> str:
        """Băm mật khẩu dạng clear-text sang bcrypt hash."""
        return self.pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Kiểm tra mật khẩu nhập vào khớp với mật khẩu đã băm."""
        return self.pwd_context.verify(plain_password, hashed_password)
