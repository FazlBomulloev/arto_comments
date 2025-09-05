from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Any
from src.db import AsyncSessionLocal, AsyncSession
from sqlalchemy.ext.asyncio import AsyncConnection
from src.db import async_engine
from asyncpg.exceptions import ConnectionDoesNotExistError
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
import asyncio
from sqlalchemy import text

@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Асинхронный контекстный менеджер для работы с сессией БД"""
    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        session = AsyncSessionLocal()
        try:
            # Проверяем соединение с помощью text()
            await session.execute(text("SELECT 1"))
            yield session
            await session.commit()
            break
        except (ConnectionDoesNotExistError, DBAPIError) as e:
            await session.rollback()
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(retry_delay)
            await session.close()
            continue
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

@asynccontextmanager
async def get_connection() -> AsyncIterator[AsyncConnection]:
    """Асинхронный контекстный менеджер для работы с подключением к БД"""
    max_retries = 3
    retry_delay = 1

    for attempt in range(max_retries):
        try:
            async with async_engine.begin() as conn:
                try:
                    # Используем text() для проверки соединения
                    await conn.execute(text("SELECT 1"))
                    yield conn
                    break
                except (ConnectionDoesNotExistError, DBAPIError) as e:
                    if attempt == max_retries - 1:
                        raise
                    await asyncio.sleep(retry_delay)
                    continue
        except Exception:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(retry_delay)
            continue