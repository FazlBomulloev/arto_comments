# migration_add_recovery_fields.py
"""
Скрипт миграции для добавления полей системы восстановления аккаунтов
Запустить один раз для обновления схемы БД
"""

import asyncio
from sqlalchemy import text
from src.db import get_session

async def run_migration():
    """Добавляет новые поля для системы восстановления"""
    
    migration_queries = [
        # Добавляем новые поля если их нет
        """
        ALTER TABLE accounts 
        ADD COLUMN IF NOT EXISTS last_error TEXT;
        """,
        """
        ALTER TABLE accounts 
        ADD COLUMN IF NOT EXISTS last_error_time TIMESTAMP;
        """,
        """
        ALTER TABLE accounts 
        ADD COLUMN IF NOT EXISTS next_check_time TIMESTAMP;
        """,
        """
        ALTER TABLE accounts 
        ADD COLUMN IF NOT EXISTS total_fails INTEGER DEFAULT 0;
        """,
        """
        ALTER TABLE accounts 
        ADD COLUMN IF NOT EXISTS pause_reason VARCHAR(50);
        """,
        
        # Обновляем существующие записи
        """
        UPDATE accounts 
        SET total_fails = 0 
        WHERE total_fails IS NULL;
        """
    ]
    
    async with get_session() as session:
        try:
            for query in migration_queries:
                print(f"Выполняем: {query.strip()}")
                await session.execute(text(query))
            
            await session.commit()
            print("✅ Миграция успешно выполнена!")
            
        except Exception as e:
            await session.rollback()
            print(f"❌ Ошибка миграции: {e}")
            raise

if __name__ == "__main__":
    print("🔄 Запуск миграции для добавления полей восстановления аккаунтов...")
    asyncio.run(run_migration())