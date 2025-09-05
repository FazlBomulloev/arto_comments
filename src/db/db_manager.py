from src.db.base import Base, async_engine
from .pool_manager import get_session, get_connection

async def init_db():
    """
    Создает все таблицы в базе данных
    """
    async with get_connection() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def drop_db():
    """
    Удаляет все таблицы из базы данных (для тестов/разработки)
    """
    async with get_connection() as conn:
        await conn.run_sync(Base.metadata.drop_all)