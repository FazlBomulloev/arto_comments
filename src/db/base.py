from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from src.cfg import config

DATABASE_URL = f"postgresql+asyncpg://{config.DB_USER}:{config.DB_PASSWORD}@{config.HOST_IP}:5432/{config.DB_NAME}"

async_engine = create_async_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,  # Пересоздавать соединения каждый час
    pool_pre_ping=True,  # Проверять соединения перед использованием
    pool_timeout=30,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
    autoflush=False,
    class_=AsyncSession
)

class Base(DeclarativeBase):
    pass