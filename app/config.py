from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    URL_BACKEND_PUBLIC: str = "http://localhost:8000"
    ALLOW_ORIGINS: str = "*"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/postgres"
    SECRET_KEY: str = "supersecretkey_reviewgen_1234567890_change_me"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    GEMINI_API_KEY: str = ""
    MODEL_ID: str = "gemini-3.1-flash-lite"

    @property
    def async_database_url(self) -> str:
        """
        Chuyển đổi URL kết nối PostgreSQL từ sync (postgresql://) sang async (postgresql+asyncpg://)
        để sử dụng với SQLAlchemy Async Engine.
        """
        if self.DATABASE_URL.startswith("postgresql://"):
            return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.DATABASE_URL

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
