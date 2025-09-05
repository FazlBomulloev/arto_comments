from redis.asyncio import Redis
import json
from src.cfg import config
from faststream.redis import RedisBroker
from src.cfg import config


class RedisClient:
    _instance = None

    @classmethod
    async def get_redis(cls):
        if cls._instance is None:
            cls._instance = config.redis_client
        return cls._instance

    @classmethod
    async def close_redis(cls):
        if cls._instance:
            await cls._instance.close()
            cls._instance = None

    @classmethod
    async def set_data(cls, key: str, value):
        redis = await cls.get_redis()
        await redis.set(key, str(value))


# Утилитные функции для работы с Redis
async def set_key(key: str, value: str):
    redis = await RedisClient.get_redis()
    await redis.set(key, value)


async def get_key(key: str):
    redis = await RedisClient.get_redis()
    return await redis.get(key)