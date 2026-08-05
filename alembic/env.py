import asyncio
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import pool
from alembic import context

# Import cấu hình và các model
from app.config import settings
from app.models.base import Base
from app.models.user import User
from app.models.gmail import GmailAccount
from app.models.proxy import Proxy
from app.models.business import Business
from app.models.history import ReviewHistory
from app.models.log import SystemLog

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Đăng ký metadata của các model để tự động sinh schema
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Chạy migration ở chế độ offline."""
    url = settings.async_database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online() -> None:
    """Chạy migration ở chế độ online (kết nối trực tiếp database)."""
    # Khởi tạo async engine từ URL cấu hình trong settings
    connectable = create_async_engine(
        settings.async_database_url,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

if context.is_offline_mode():
    run_migrations_offline()
else:
    # Khởi chạy luồng async
    asyncio.run(run_migrations_online())
