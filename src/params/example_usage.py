import asyncio
from db_manager import DatabaseManager

async def main():
    # Использование контекстного менеджера
    async with DatabaseManager() as db:
        # Пример работы с параметрами
        await db.set_parameter("api_key", "12345-async")
        value = await db.get_parameter("api_key")
        print(f"Получен параметр: {value}")

        # Пример работы с used_list
        await db.add_used_item(
            channel_id=1,
            first_name="Алексей",
            second_name="Петров",
            images="async_profile.jpg"
        )

        # Получение использованных данных
        used_items = await db.get_used_items(channel_id=1)
        print(f"Used items: {used_items}")