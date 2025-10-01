# src/storage/redis_manager.py
import json
from typing import Optional, Any, Dict, List
from redis.asyncio import Redis
from redis.exceptions import RedisError
import logging
from src.cfg import config
logger = logging.getLogger(__name__)


class RedisManager:
    def __init__(self, redis_url: str = config.REDIS_URL):  # Используем REDIS_URL
        self.redis_url = redis_url
        self.connection: Optional[Redis] = None

    async def connect(self) -> None:
        if not self.connection or await self._check_connection() is False:
            try:
                self.connection = Redis.from_url(
                    self.redis_url,
                    socket_timeout=5,
                    socket_keepalive=True,
                    retry_on_timeout=True,
                )
                await self.connection.ping()
                logger.info("Redis connection established")
            except RedisError as e:
                logger.error(f"Redis connection error: {e}")
                raise

    async def _check_connection(self) -> bool:
        try:
            return await self.connection.ping()
        except (RedisError, AttributeError):
            return False

    async def set_data(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        try:
            await self.connect()
            serialized = json.dumps(value)
            if expire:
                await self.connection.setex(key, expire, serialized)
            else:
                await self.connection.set(key, serialized)
            return True
        except (RedisError, ValueError) as e:  # Заменяем JSONEncodeError на ValueError
            logger.error(f"Redis set_data error: {e}")
            return False

    async def get_data(self, key: str) -> Optional[Any]:
        try:
            await self.connect()
            data = await self.connection.get(key)
            if data:
                return json.loads(data)
            return None
        except (RedisError, ValueError) as e:  # Заменяем JSONDecodeError на ValueError
            logger.error(f"Redis get_data error: {e}")
            return None

    async def delete_data(self, key: str) -> bool:
        """Удаляет данные по ключу"""
        try:
            await self.connect()
            return bool(await self.connection.delete(key))  # type: ignore
        except RedisError as e:
            logger.error(f"Redis delete_data error: {e}")
            return False

    async def get_all_keys(self, pattern: str = "*") -> List[str]:
        """Получает все ключи по шаблону"""
        try:
            await self.connect()
            return await self.connection.keys(pattern)  # type: ignore
        except RedisError as e:
            logger.error(f"Redis get_all_keys error: {e}")
            return []

    async def hash_set(self, name: str, mapping: Dict[str, Any]) -> bool:
        """Устанавливает значения в хэш"""
        try:
            await self.connect()
            serialized = {k: json.dumps(v) for k, v in mapping.items()}
            await self.connection.hset(name, mapping=serialized)  # type: ignore
            return True
        except (RedisError, json.JSONEncodeError) as e:
            logger.error(f"Redis hash_set error: {e}")
            return False

    async def hash_get(self, name: str, key: str) -> Optional[Any]:
        """Получает значение из хэша"""
        try:
            await self.connect()
            data = await self.connection.hget(name, key)  # type: ignore
            if data:
                return json.loads(data)
            return None
        except (RedisError, json.JSONDecodeError) as e:
            logger.error(f"Redis hash_get error: {e}")
            return None

    async def publish(self, channel: str, message: Any) -> bool:
        """Публикует сообщение в Redis-канал"""
        try:
            await self.connect()
            await self.connection.publish(channel, json.dumps(message))  # type: ignore
            return True
        except (RedisError, json.JSONEncodeError) as e:
            logger.error(f"Redis publish error: {e}")
            return False