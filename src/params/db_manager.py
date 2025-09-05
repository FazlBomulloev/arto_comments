import aiosqlite
from typing import Optional, Dict, List, Tuple, AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

class DatabaseManager:
    def __init__(self, db_path: str = "src/params/database.db"):
        self.db_path = db_path

    @asynccontextmanager
    async def _get_connection(self) -> AsyncIterator[aiosqlite.Connection]:
        """Контекстный менеджер для подключения к БД."""
        conn = await aiosqlite.connect(self.db_path)
        try:
            # Включаем поддержку внешних ключей
            await conn.execute("PRAGMA foreign_keys = ON")
            yield conn
        finally:
            await conn.close()

    async def _init_db(self) -> None:
        """Инициализирует базу данных и таблицы."""
        async with self._get_connection() as conn:
            cursor = await conn.cursor()
            # Таблица параметров
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS parameters (
                    name TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            # Таблица использованных данных
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS used_list (
                    channel_id INTEGER,
                    first_name TEXT,
                    second_name TEXT,
                    images TEXT,
                    PRIMARY KEY (channel_id, first_name, second_name, images)
                )
            """)
            await conn.commit()

    async def set_parameter(self, name: str, value: str) -> None:
        """Устанавливает параметр."""
        async with self._get_connection() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO parameters (name, value) VALUES (?, ?)",
                (name, value)
            )
            await conn.commit()

    async def get_parameter(self, name: str) -> Optional[str]:
        """Возвращает значение параметра."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                "SELECT value FROM parameters WHERE name = ?",
                (name,)
            )
            result = await cursor.fetchone()
            return result[0] if result else None

    async def add_used_item(
        self,
        channel_id: int,
        first_name: str,
        second_name: str,
        images: str
    ) -> None:
        """Добавляет запись в used_list."""
        async with self._get_connection() as conn:
            await conn.execute(
                """
                INSERT INTO used_list (channel_id, first_name, second_name, images)
                VALUES (?, ?, ?, ?)
                """,
                (channel_id, first_name, second_name, images)
            )
            await conn.commit()

    async def get_used_items(self, channel_id: int) -> List[Tuple[str, str, str]]:
        """Возвращает использованные данные для канала."""
        async with self._get_connection() as conn:
            cursor = await conn.execute(
                """
                SELECT first_name, second_name, images
                FROM used_list
                WHERE channel_id = ?
                """,
                (channel_id,)
            )
            return await cursor.fetchall()

    async def get_delay_parameters(self) -> Tuple[float, float]:
        """Возвращает базовую задержку и разброс из параметров."""
        base_delay = float(await self.get_parameter("comment_delay") or "5.0")
        delay_spread = float(await self.get_parameter("comment_range") or "3.0")
        return base_delay, delay_spread

    async def __aenter__(self):
        """Контекстный менеджер для инициализации БД при входе."""
        await self._init_db()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Контекстный менеджер для закрытия ресурсов при выходе."""
        pass  # Все соединения закрываются в _get_connection