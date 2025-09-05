# handlers.py
import logging
from datetime import datetime, timedelta

from aiogram import Router
from aiogram.types import Message
from src.db.models import Channel, AIAgent, Account, PostActivity
from src.db import get_session
from src.ai.requests import request
from sqlalchemy import select, func, and_
import random
from typing import List
from aiogram import F
from src.tasks.tasks import CommentTask, CommentTaskMessage, LikeCommentTask, LikeCommentTaskMessage
from src.cfg import config

broker = config.broker

router = Router()

logger = logging.getLogger(__name__)

def clean_comments(raw_comments: str) -> List[str]:
    """
    Очищает комментарии от нумерации и возвращает список чистых комментариев.
    Обрабатывает три разных формата комментариев из примера.
    """
    comments = []
    for line in raw_comments.split('\n'):
        line = line.strip()
        if not line:
            continue

        if line[0].isdigit() and '.' in line:
            comment = line.split('.', 1)[1].strip()
            comments.append(comment)

        elif line[0].isdigit() and '"' in line:
            comment = line.split('"', 1)[1].rsplit('"', 1)[0]
            comments.append(comment)

        elif line[0].isdigit() and '_' in line:
            comment = line.split('_', 1)[1].rsplit('_', 1)[0]
            comments.append(comment)

        # Если строка не содержит цифр в начале - добавляем как есть
        else:
            comments.append(line)

    return comments

async def get_random_accounts(session, count: int, channel_id: int) -> List[Account]:
    """Возвращает список случайных активных аккаунтов для канала."""
    result = await session.execute(
        select(Account)
        .where(Account.status == 'active')
        .where(Account.channel_id == channel_id)
        .order_by(func.random())
        .limit(count)
    )
    return result.scalars().all()

async def should_comment_on_post(session, channel: Channel, channel_username: str, post_id: int) -> bool:
    """Проверяет, стоит ли комментировать данный пост на основе настроек канала"""
    
    # 1. Проверяем базовый шанс комментирования
    if random.randint(1, 100) > channel.comments_chance:
        logger.debug(f"Пост {post_id} пропущен по базовому шансу комментирования")
        return False
    
    # 2. Проверяем шанс выбора поста
    if random.randint(1, 100) > channel.posts_selection_chance:
        logger.debug(f"Пост {post_id} пропущен по шансу выбора поста")
        return False
    
    # 3. Проверяем интервал между постами
    last_activity = await session.execute(
        select(PostActivity)
        .where(PostActivity.channel_name == channel_username)
        .order_by(PostActivity.last_comment_time.desc())
        .limit(1)
    )
    last_activity = last_activity.scalar_one_or_none()
    
    if last_activity:
        time_since_last = datetime.now() - last_activity.last_comment_time
        min_interval = timedelta(minutes=channel.posts_min_interval)
        
        if time_since_last < min_interval:
            logger.debug(f"Пост {post_id} пропущен - слишком рано после последнего комментария")
            return False
    
    return True

async def update_post_activity(session, channel_username: str, post_id: int, comments_count: int, likes_count: int):
    """Обновляет статистику активности по посту"""
    activity = await session.execute(
        select(PostActivity)
        .where(and_(
            PostActivity.channel_name == channel_username,
            PostActivity.post_id == post_id
        ))
    )
    activity = activity.scalar_one_or_none()
    
    if activity:
        activity.last_comment_time = datetime.now()
        activity.total_comments += comments_count
        activity.total_likes += likes_count
    else:
        new_activity = PostActivity(
            channel_name=channel_username,
            post_id=post_id,
            last_comment_time=datetime.now(),
            total_comments=comments_count,
            total_likes=likes_count
        )
        session.add(new_activity)

@router.message(F.chat.type == 'supergroup', F.sender_chat.id != F.chat.id)
async def post_commenting(message: Message):
    async with get_session() as session:
        try:
            # Получаем канал из БД
            channel = await session.execute(
                select(Channel).where(Channel.name == message.chat.username)
            )
            channel = channel.scalar_one_or_none()

            if not channel:
                logger.debug(f"Канал {message.chat.username} не найден в базе")
                return

            # Проверяем, стоит ли комментировать этот пост
            if not await should_comment_on_post(session, channel, message.chat.username, message.message_id):
                return

            # Получаем активного агента
            agent = await session.execute(
                select(AIAgent)
                .where(
                    AIAgent.channel_id == channel.id,
                    AIAgent.status == True
                )
            )
            agent = agent.scalar_one_or_none()

            if not agent:
                logger.info(f"Для канала {channel.name} не найден активный агент")
                return

            # Получаем ответ от ИИ
            response = await request(
                agent_id=agent.api_id,
                content=message.text or message.caption or ""
            )
            comments = clean_comments(response)

            # Рассчитываем количество комментариев
            comments_count = channel.comments_number
            comments_spread = channel.comments_number_range
            actual_count = max(1, min(
                comments_count + random.randint(-comments_spread, comments_spread),
                len(comments)
            ))
            selected_comments = random.sample(comments, actual_count) if comments else []

            # Получаем случайные аккаунты для комментариев
            accounts = await get_random_accounts(session, actual_count, channel.id)
            if not accounts:
                logger.info("Нет доступных аккаунтов для комментариев")
                return

            # Парсим типы реакций для лайков
            reaction_types = [r.strip() for r in channel.likes_reaction_types.split(',') if r.strip()]

            # Создаем задачи на комментирование
            comment_tasks = []
            for i, comment in enumerate(selected_comments):
                if i < len(accounts):
                    task = CommentTask(
                        account_session=accounts[i].session,
                        account_number=accounts[i].number,
                        channel=message.chat.username,
                        channel_id=channel.id,
                        post_id=message.message_id,
                        comment_text=comment,
                        delay=random.uniform(5, 15),
                        like_chance=channel.likes_on_posts_chance,
                        reaction_types=reaction_types
                    )
                    comment_tasks.append(task)

            # Отправляем задачи комментирования в брокер
            try:
                logger.info(f"Отправка {len(comment_tasks)} задач комментирования в брокер")
                await broker.connect()

                result = await broker.publish(
                    message=CommentTaskMessage(data=comment_tasks),
                    channel="comment_tasks"
                )
                logger.info(f"Задачи комментирования отправлены. Результат: {result}")

                # Создаем задачи на лайки комментариев других аккаунтов
                if channel.likes_on_comments_chance > 0:
                    like_tasks = await create_comment_like_tasks(
                        session, channel, message.chat.username, 
                        comment_tasks, reaction_types
                    )
                    
                    if like_tasks:
                        await broker.publish(
                            message=LikeCommentTaskMessage(data=like_tasks),
                            channel="like_comment_tasks"
                        )
                        logger.info(f"Отправлено {len(like_tasks)} задач лайков комментариев")

                await broker.close()

                # Обновляем статистику активности
                await update_post_activity(
                    session, message.chat.username, message.message_id, 
                    len(comment_tasks), 0  # лайки будут подсчитаны позже
                )
                await session.commit()

            except Exception as e:
                logger.error(f"Ошибка при работе с брокером: {str(e)}")
                raise

        except Exception as e:
            logger.error(f"Ошибка в post_commenting: {str(e)}")
            await session.rollback()
            raise

async def create_comment_like_tasks(
    session, channel: Channel, channel_username: str, 
    comment_tasks: List[CommentTask], reaction_types: List[str]
) -> List[LikeCommentTask]:
    """Создает задачи на лайки комментариев других аккаунтов"""
    like_tasks = []
    
    # Получаем все аккаунты канала для лайков
    all_accounts = await session.execute(
        select(Account)
        .where(Account.channel_id == channel.id)
        .where(Account.status == 'active')
    )
    all_accounts = all_accounts.scalars().all()
    
    if len(all_accounts) < 2:  # Нужно минимум 2 аккаунта
        return like_tasks
    
    for comment_task in comment_tasks:
        # Выбираем аккаунты, которые могут лайкнуть этот комментарий (исключая автора)
        potential_likers = [acc for acc in all_accounts if acc.number != comment_task.account_number]
        
        # Определяем количество лайков для этого комментария (1-3)
        likes_count = random.randint(1, min(3, len(potential_likers)))
        likers = random.sample(potential_likers, likes_count)
        
        for liker in likers:
            # Проверяем шанс лайка
            if random.randint(1, 100) <= channel.likes_on_comments_chance:
                # Задержка для лайка (после отправки комментария + дополнительная задержка)
                like_delay = comment_task.delay + random.uniform(30, 180)  # 30сек - 3мин после комментария
                
                like_task = LikeCommentTask(
                    account_session=liker.session,
                    account_number=liker.number,
                    channel=channel_username,
                    comment_id=0,  # будет установлен после отправки комментария
                    target_comment_account=comment_task.account_number,
                    delay=like_delay,
                    reaction_types=reaction_types
                )
                like_tasks.append(like_task)
    
    return like_tasks