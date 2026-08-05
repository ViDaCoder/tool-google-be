from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """
    Lớp cơ sở trừu tượng cho tất cả các SQLAlchemy Models.
    Chứa registry và metadata cần thiết cho Alembic migrations.
    """
    pass
