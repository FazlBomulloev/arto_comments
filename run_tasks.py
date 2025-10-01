import asyncio
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler

from src.tasks.tasks import app as tasks_app
from src.cfg import config
from src.db.db_manager import init_db
from src.utils.uvloop_manager import UVLoopManager


async def main():
    # Настройка логирования
    log_file = Path(__file__).parent.absolute() / 'logs' / 'tasks.log'

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - [%(filename)s:%(lineno)d] - %(levelname)s - %(message)s',
        handlers=[
            RotatingFileHandler(
                log_file,
                maxBytes=100 * 1024 * 1024,
                backupCount=5,
                encoding='utf-8'
            ),
            logging.StreamHandler()
        ]
    )
    logger = logging.getLogger(__name__)

    # Установка uvloop (если доступно)
    uvloop_manager = UVLoopManager()
    uvloop_manager.install()

    # Инициализация БД
    try:
        await init_db()
        logger.info("Database connected successfully")
    except Exception as e:
        logger.error(f"Database connection error: {str(e)[:200]}")
        return

    # Запуск обработчика задач
    try:
        logger.info("Starting tasks processor")
        await tasks_app.run()
    except KeyboardInterrupt:
        logger.info("Tasks processor stopped by user")
    except Exception as e:
        logger.critical(f"Tasks processor error: {str(e)[:200]}")
    finally:
        logger.info("Tasks processor stopped")


if __name__ == "__main__":
    asyncio.run(main())