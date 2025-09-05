import asyncio
import json
import logging
import random
import time
from typing import List
from datetime import datetime

from faststream import FastStream, Logger
from pydantic import BaseModel
from sqlalchemy import select, and_

from .redis_utils import RedisClient
from src.cfg import config
from src.db import get_session
from src.db.models import Account, CommentActivity
from src.params.db_manager import DatabaseManager

broker = config.broker

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [%(filename)s:%(lineno)d] - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Константы Redis
TASK_QUEUE_PREFIX = "arto_task:"
TASK_TYPE = "comment_task"

app = FastStream(broker)

from .task_models import CommentTask, CommentTaskMessage, LikeCommentTask, LikeCommentTaskMessage

async def save_task_to_redis(task_data: dict) -> str:
    """Сохранение задачи в Redis"""
    try:
        redis = await RedisClient.get_redis()
        task_id = f"{TASK_QUEUE_PREFIX}{time.time_ns()}"

        if not task_data:
            raise ValueError("Пустые данные задачи")

        task_json = json.dumps(task_data, ensure_ascii=False)

        logger.debug(f"Сохранение задачи в Redis. ID: {task_id}, данные: {task_data}")

        await redis.hset(task_id, mapping={
            "type": TASK_QUEUE_PREFIX.rstrip(':'),
            "data": task_json,
            "created_at": str(time.time()),
            "status": "pending",
            "attempts": "0"
        })
        await redis.expire(task_id, 86400)
        return task_id
    except Exception as e:
        logger.error(f"Ошибка сохранения задачи: {e}")
        raise

async def execute_and_delete_task(task_id: str, processor: callable, args: list):
    """Выполняет задачу и удаляет её из Redis"""
    redis = await RedisClient.get_redis()
    try:
        logger.info(f"Начало выполнения задачи {task_id}")

        result = await processor(*args)
        await redis.delete(task_id)

        logger.info(f"Задача {task_id} успешно выполнена и удалена")
        return result
    except Exception as e:
        logger.error(f"Ошибка выполнения задачи {task_id}: {e}")
        await redis.delete(task_id)
        raise

async def execute_delayed_task(task_id: str, processor: callable, args: list, delay: float):
    """Выполняет задачу после указанной задержки"""
    try:
        if delay > 0:
            logger.debug(f"Задача {task_id}: ожидание {delay} сек перед выполнением")
            await asyncio.sleep(delay)

        logger.debug(f"Задача {task_id}: начало выполнения после задержки")
        return await execute_and_delete_task(task_id, processor, args)

    except Exception as e:
        logger.error(f"Ошибка выполнения отложенной задачи {task_id}: {e}")
        raise

@broker.subscriber("comment_tasks")
async def handle_comment_tasks(msg: CommentTaskMessage):
    """Обработчик задач комментирования с накапливающейся задержкой"""
    try:
        logger.info(f"Получена новая партия задач: {len(msg.data)} комментариев")

        # Получаем параметры задержки из БД
        db_manager = DatabaseManager()
        async with db_manager:
            base_delay, delay_spread = await db_manager.get_delay_parameters()

            # Конвертируем минуты в секунды
            base_delay = base_delay * 60
            delay_spread = delay_spread * 60

        task_ids = []
        cumulative_delay = 0.0

        for item in msg.data:
            try:
                # Генерируем случайную задержку в пределах разброса
                current_delay = base_delay + random.uniform(-delay_spread, delay_spread)
                current_delay = max(0.1, current_delay)

                # Добавляем к накопительной задержке
                cumulative_delay += current_delay
                item.delay = cumulative_delay

                logger.info(f"Задача для канала {item.channel}: задержка {cumulative_delay:.2f} сек")

                task_id = await save_task_to_redis(item.model_dump())
                task_ids.append(task_id)

                asyncio.create_task(
                    execute_delayed_task(
                        task_id,
                        process_comment_task,
                        [item],
                        cumulative_delay
                    )
                )

            except Exception as e:
                logger.error(f"Ошибка обработки отдельной задачи: {e}")
                continue

        logger.info(f"Успешно создано {len(task_ids)} задач с накапливающейся задержкой")
        return {"status": "success", "task_ids": task_ids}

    except Exception as e:
        logger.error(f"Критическая ошибка обработки задач комментирования: {e}")
        raise

@broker.subscriber("like_comment_tasks")
async def handle_like_comment_tasks(msg: LikeCommentTaskMessage):
    """Обработчик задач лайков комментариев"""
    try:
        logger.info(f"Получена новая партия задач лайков: {len(msg.data)} лайков")

        task_ids = []
        for item in msg.data:
            try:
                task_id = await save_task_to_redis(item.model_dump())
                task_ids.append(task_id)

                asyncio.create_task(
                    execute_delayed_task(
                        task_id,
                        process_like_comment_task,
                        [item],
                        item.delay
                    )
                )

            except Exception as e:
                logger.error(f"Ошибка обработки задачи лайка: {e}")
                continue

        logger.info(f"Успешно создано {len(task_ids)} задач лайков комментариев")
        return {"status": "success", "task_ids": task_ids}

    except Exception as e:
        logger.error(f"Критическая ошибка обработки задач лайков: {e}")
        raise

async def process_comment_task(task: CommentTask):
    """Обработка одной задачи комментирования"""
    from src.accounts.comment import post_comment_with_session
    from telethon.tl.types import ReactionEmoji

    class MockChat:
        def __init__(self, username):
            self.username = username
            self.type = 'supergroup'

    class MockMessage:
        def __init__(self, chat, message_id):
            self.chat = chat
            self.message_id = message_id

    try:
        logger.info(f"Начало обработки комментария для канала {task.channel}, пост {task.post_id}")

        mock_chat = MockChat(task.channel)
        mock_message = MockMessage(mock_chat, task.post_id)

        # Подготавливаем реакции
        available_reactions = [ReactionEmoji(emoticon=emoji) for emoji in task.reaction_types]

        result = await post_comment_with_session(
            session_data=task.account_session,
            message=mock_message,
            comment_text=task.comment_text,
            like_chance=task.like_chance,
            available_reactions=available_reactions
        )

        # Обновляем статистику в БД
        async with get_session() as session:
            account = await session.get(Account, task.account_number)
            if account:
                if result["comment_sent"]:
                    account.comments_sent += 1
                if result["like_given"]:
                    account.likes_given += 1
                account.last_activity = datetime.now()
                
                # Записываем информацию о комментарии для будущих лайков
                if result["comment_sent"] and result["comment_id"]:
                    comment_activity = CommentActivity(
                        channel_name=task.channel,
                        post_id=task.post_id,
                        comment_id=result["comment_id"],
                        account_number=task.account_number
                    )
                    session.add(comment_activity)
                
                await session.commit()

        if result["success"]:
            logger.info(f"Комментарий успешно отправлен в канал {task.channel}")
        else:
            logger.warning(f"Не удалось отправить комментарий в канал {task.channel}: {result.get('error')}")

        return result

    except Exception as e:
        logger.error(f"Ошибка обработки задачи комментирования (канал {task.channel}): {e}")
        raise

async def process_like_comment_task(task: LikeCommentTask):
    """Обработка одной задачи лайка комментария"""
    from src.accounts.comment import like_comment_with_session
    from telethon.tl.types import ReactionEmoji

    try:
        logger.info(f"Начало обработки лайка комментария в канале {task.channel}")

        # Если comment_id не указан, ищем комментарий по аккаунту
        comment_id = task.comment_id
        if comment_id == 0:
            async with get_session() as session:
                # Ищем последний комментарий от целевого аккаунта
                comment_activity = await session.execute(
                    select(CommentActivity)
                    .where(and_(
                        CommentActivity.channel_name == task.channel,
                        CommentActivity.account_number == task.target_comment_account
                    ))
                    .order_by(CommentActivity.created_at.desc())
                    .limit(1)
                )
                comment_activity = comment_activity.scalar_one_or_none()
                
                if comment_activity:
                    comment_id = comment_activity.comment_id
                else:
                    logger.warning(f"Не найден комментарий для лайка от {task.target_comment_account}")
                    return False

        # Подготавливаем реакции
        available_reactions = [ReactionEmoji(emoticon=emoji) for emoji in task.reaction_types]

        success = await like_comment_with_session(
            session_data=task.account_session,
            channel_username=task.channel,
            comment_id=comment_id,
            available_reactions=available_reactions
        )

        # Обновляем статистику
        if success:
            async with get_session() as session:
                account = await session.get(Account, task.account_number)
                if account:
                    account.likes_given += 1
                    account.last_activity = datetime.now()

                # Обновляем статистику комментария
                comment_activity = await session.execute(
                    select(CommentActivity)
                    .where(CommentActivity.comment_id == comment_id)
                )
                comment_activity = comment_activity.scalar_one_or_none()
                if comment_activity:
                    comment_activity.likes_received += 1

                await session.commit()

        return success

    except Exception as e:
        logger.error(f"Ошибка обработки задачи лайка комментария: {e}")
        raise

async def restore_tasks():
    """Восстановление задач при старте"""
    try:
        logger.info("Начало восстановления задач из Redis")
        redis = await RedisClient.get_redis()
        restored = 0

        async for key in redis.scan_iter(match=f"{TASK_QUEUE_PREFIX}*"):
            try:
                task_data = await redis.hgetall(key)

                if not task_data or b'data' not in task_data:
                    logger.warning(f"Пропускаем задачу {key}: отсутствуют данные")
                    await redis.delete(key)
                    continue

                try:
                    task_dict = json.loads(task_data[b'data'].decode('utf-8'))
                    
                    # Определяем тип задачи и создаем соответствующий объект
                    if 'comment_text' in task_dict:
                        task_obj = CommentTask(**task_dict)
                        processor = process_comment_task
                    elif 'comment_id' in task_dict:
                        task_obj = LikeCommentTask(**task_dict)
                        processor = process_like_comment_task
                    else:
                        logger.warning(f"Неизвестный тип задачи: {key}")
                        await redis.delete(key)
                        continue

                    # Проверяем TTL задачи
                    ttl = await redis.ttl(key)
                    if ttl < 0:
                        logger.warning(f"Задача {key} истекла, пропускаем")
                        await redis.delete(key)
                        continue

                    logger.info(f"Восстановление задачи {key.decode()}")

                    asyncio.create_task(
                        execute_delayed_task(
                            key.decode(),
                            processor,
                            [task_obj],
                            task_obj.delay
                        )
                    )
                    restored += 1

                except json.JSONDecodeError:
                    logger.error(f"Ошибка декодирования JSON для задачи {key}")
                    await redis.delete(key)

            except Exception as e:
                logger.error(f"Ошибка восстановления задачи {key}: {e}")
                continue

        logger.info(f"Всего восстановлено задач: {restored}")
        return restored
    except Exception as e:
        logger.error(f"Ошибка при восстановлении задач: {e}")
        raise

async def cleanup_broken_tasks():
    """Очистка битых задач из Redis"""
    try:
        redis = await RedisClient.get_redis()
        deleted = 0

        async for key in redis.scan_iter(match=f"{TASK_QUEUE_PREFIX}*"):
            task_data = await redis.hgetall(key)
            if not task_data or b'data' not in task_data:
                await redis.delete(key)
                deleted += 1

        logger.info(f"Удалено битых задач: {deleted}")
        return deleted
    except Exception as e:
        logger.error(f"Ошибка очистки битых задач: {e}")
        raise

@app.on_startup
async def on_startup():
    """Действия при старте приложения"""
    try:
        logger.info("Запуск обработчика задач...")
        await cleanup_broken_tasks()
        await restore_tasks()
    except Exception as e:
        logger.critical(f"Ошибка при старте: {e}")
        raise

@app.on_shutdown
async def on_shutdown():
    """Действия при остановке приложения"""
    try:
        logger.info("Завершение работы обработчика задач...")
        await RedisClient.close_redis()
        logger.info("Redis соединение закрыто")
    except Exception as e:
        logger.error(f"Ошибка при завершении работы: {e}")