import os, dotenv
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage, DefaultKeyBuilder
from faststream.redis import RedisBroker
from redis.asyncio import Redis

dotenv.load_dotenv()
class config:

    bot = Bot(token=os.getenv("BOT_TOKEN"), default=DefaultBotProperties(parse_mode='HTML'))

    # Добавляем строку подключения отдельно
    REDIS_PASSWORD=os.getenv('REDIS_PASSWORD')
    REDIS_URL = f"redis://:{REDIS_PASSWORD}@{os.getenv('IP')}:6379"
    broker = RedisBroker(REDIS_URL)
    redis_client = Redis.from_url(REDIS_URL)
    storage = RedisStorage(redis=redis_client, key_builder=DefaultKeyBuilder(with_destiny=True))
    dp = Dispatcher(storage=storage)

    CHANNEL_ID = os.getenv("CHANNEL_ID")
    ADMIN_LIST = os.getenv("ADMINS").split(',')
    PORT = os.getenv("PORT")
    DB_NAME = os.getenv("DB_NAME")
    DB_PASSWORD = os.getenv('DB_PASSWORD')
    HOST_PASSWORD = os.getenv("HOST_PASSWORD")
    HOST_IP = os.getenv("IP")
    DB_USER = os.getenv("DB_USER")
    AI_TOKEN = os.getenv('AI_TOKEN')
    API_ID = os.getenv('API_ID')
    API_HASH = os.getenv('API_HASH')
