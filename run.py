import asyncio
import logging
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler

from aiogram import Router

from src.cfg import config
import sys
from src.utils.uvloop_manager import UVLoopManager
from src.utils.params_manager import init_default_params
from aiogram_dialog import setup_dialogs
from src.interfaces import get_all_routers
from src.accounts.handlers import router as comments_router
from src.params.db_manager import DatabaseManager
from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis

from src.db.db_manager import init_db, drop_db


sys.stdout.reconfigure(encoding='utf-8')


async def main():

    uvloop_manager = UVLoopManager()
    bot = config.bot
    dp = config.dp

    # 1. Настройка логирования с ротацией
    log_file = Path(__file__).parent.absolute() / 'logs' / 'app.log'

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(filename)s:%(lineno)d] - %(levelname)s - %(message)s',  # Упрощенный формат
        handlers=[
            RotatingFileHandler(
                log_file,
                maxBytes=100 * 1024 * 1024,  # 10 МБ на файл
                backupCount=5,  # 5 файлов ротации (итого 50 МБ)
                encoding='utf-8',
                delay=False  # Не откладывать запись
            ),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)

    uvloop_manager.install()

    # 2. Подключение к БД
    try:
        await init_db()
        logger.info("POSTGRES DB connected")
    except Exception as e:
        logger.error(f"DB error: {str(e)[:100]}")  # Ограничение длины ошибки
        return

    try:
        async with DatabaseManager() as db:
            # Можно добавить начальные параметры, если нужно
            await db.set_parameter("bot_started", str(datetime.now()))
            await init_default_params()
            logging.info("PARAMS DB initialized")
    except Exception as e:
        logger.error(f"PARAMS DB error: {str(e)[:100]}")  # Ограничение длины ошибки
        return

    logger.info("=== Bot starting ===")


    # 3. Подключение роутеров
    [dp.include_router(router) for router in get_all_routers()]
    dp.include_router(comments_router)
    setup_dialogs(dp)

    # 4. Запуск бота
    try:
        logger.info("Starting bot polling")
        await dp.start_polling(bot, skip_updates=True)
    except Exception as e:
        logger.critical(f"Bot crash: {str(e)[:200]}")  # Ограниченная длина
    finally:
        await bot.session.close()
        logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Stopped by user")
    except Exception as e:
        logging.critical(f"Fatal: {str(e)[:200]}")