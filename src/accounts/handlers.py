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
    Поддерживает формат: (1) текст, (2) текст, и т.д.
    ИСПРАВЛЕНО: полностью убирает нумерацию из итоговых комментариев.
    """
    comments = []
    
    logger.info(f"🔍 [PARSE] Начинаем парсинг ответа ИИ...")
    logger.info(f"📄 [PARSE] Исходный текст: {raw_comments[:500]}...")
    
    # Разбиваем текст на строки
    lines = raw_comments.split('\n')
    logger.info(f"📄 [PARSE] Найдено строк: {len(lines)}")
    
    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
            
        logger.debug(f"📄 [PARSE] Обрабатываем строку {i+1}: '{line[:100]}...'")
        
        comment = None
        
        # Формат: (1) комментарий, (2) комментарий и т.д.
        if line.startswith('(') and ')' in line:
            # Ищем закрывающую скобку
            closing_paren = line.find(')')
            if closing_paren != -1:
                comment = line[closing_paren + 1:].strip()
                    
        # Формат: 1) комментарий, 2) комментарий и т.д.
        elif line and line[0].isdigit() and ')' in line:
            comment = line.split(')', 1)[1].strip()
                
        # Формат: 1. комментарий, 2. комментарий и т.д.
        elif line and line[0].isdigit() and '.' in line:
            comment = line.split('.', 1)[1].strip()
        
        # Если нашли комментарий
        if comment and len(comment) > 5:
            # ДОПОЛНИТЕЛЬНАЯ ОЧИСТКА: убираем любую оставшуюся нумерацию в начале
            # Убираем паттерны типа "(14)" или "14)" или "14." в начале строки
            import re
            comment = re.sub(r'^\s*\(\d+\)\s*', '', comment)  # Убираем (14) в начале
            comment = re.sub(r'^\s*\d+\)\s*', '', comment)    # Убираем 14) в начале  
            comment = re.sub(r'^\s*\d+\.\s*', '', comment)    # Убираем 14. в начале
            
            # Убираем лишние пробелы
            comment = ' '.join(comment.split())
            
            # Проверяем что комментарий не пустой после очистки
            if len(comment) > 5:
                comments.append(comment)
                logger.info(f"✅ [CLEAN] Очищенный комментарий: '{comment[:100]}...'")
            else:
                logger.debug(f"⚠️ [CLEAN] Комментарий слишком короткий после очистки: '{comment}'")
    
    logger.info(f"📊 [PARSE] Итого найдено комментариев: {len(comments)}")
    
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

async def should_comment_on_post(session, channel: Channel, channel_name: str, post_id: int) -> bool:
    """Проверяет, стоит ли комментировать данный пост на основе настроек канала"""
    
    logger.info(f"🎲 [CHANCE] Начинаем проверку шансов для поста {post_id}")
    
    # 1. Проверяем базовый шанс комментирования
    base_roll = random.randint(1, 100)
    logger.info(f"🎲 [CHANCE] Базовый шанс: {base_roll} vs {channel.comments_chance}%")
    if base_roll > channel.comments_chance:
        logger.info(f"❌ [CHANCE] Пост {post_id} пропущен по базовому шансу комментирования ({base_roll} > {channel.comments_chance})")
        return False
    logger.info(f"✅ [CHANCE] Базовый шанс пройден")
    
    # 2. Проверяем шанс выбора поста
    selection_roll = random.randint(1, 100)
    logger.info(f"🎲 [CHANCE] Шанс выбора поста: {selection_roll} vs {channel.post_selection_chance}%")
    if selection_roll > channel.post_selection_chance:
        logger.info(f"❌ [CHANCE] Пост {post_id} пропущен по шансу выбора поста ({selection_roll} > {channel.post_selection_chance})")
        return False
    logger.info(f"✅ [CHANCE] Шанс выбора поста пройден")
    
    # 3. Проверяем интервал между постами
    logger.info(f"⏰ [INTERVAL] Проверяем интервал между постами...")
    last_activity = await session.execute(
        select(PostActivity)
        .where(PostActivity.channel_name == channel_name)
        .order_by(PostActivity.last_comment_time.desc())
        .limit(1)
    )
    last_activity = last_activity.scalar_one_or_none()
    
    if last_activity:
        time_since_last = datetime.now() - last_activity.last_comment_time
        min_interval = timedelta(minutes=channel.post_min_interval)
        
        logger.info(f"⏰ [INTERVAL] Последняя активность: {last_activity.last_comment_time}")
        logger.info(f"⏰ [INTERVAL] Время с последней активности: {time_since_last}")
        logger.info(f"⏰ [INTERVAL] Минимальный интервал: {min_interval}")
        
        if time_since_last < min_interval:
            logger.info(f"❌ [INTERVAL] Пост {post_id} пропущен - слишком рано после последнего комментария")
            logger.info(f"    Нужно подождать еще: {min_interval - time_since_last}")
            return False
        logger.info(f"✅ [INTERVAL] Интервал соблюден")
    else:
        logger.info(f"ℹ️ [INTERVAL] Нет предыдущей активности, можно комментировать")
    
    logger.info(f"🎉 [CHANCE] Все проверки пройдены! Пост {post_id} будет прокомментирован")
    return True

async def update_post_activity(session, channel_name: str, post_id: int, comments_count: int, likes_count: int):
    """Обновляет статистику активности по посту"""
    activity = await session.execute(
        select(PostActivity)
        .where(and_(
            PostActivity.channel_name == channel_name,
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
            channel_name=channel_name,
            post_id=post_id,
            last_comment_time=datetime.now(),
            total_comments=comments_count,
            total_likes=likes_count
        )
        session.add(new_activity)

async def find_channel_by_group_id(session, group_id: int, sender_chat_id: int = None) -> Channel:
    """Находит канал по ID группы обсуждений с автосвязыванием"""
    
    # Сначала ищем среди уже определенных ID групп
    result = await session.execute(
        select(Channel).where(Channel.discussion_group_id == group_id)
    )
    channel = result.scalar_one_or_none()
    
    if channel:
        logger.info(f"✅ [FIND] Канал найден по discussion_group_id: {channel.name}")
        return channel
    
    # Если не найден и есть sender_chat_id, пытаемся найти по ID канала-отправителя
    if sender_chat_id:
        logger.info(f"🔍 [FIND] Ищем канал по ID отправителя: {sender_chat_id}")
        
        # Попробуем разные варианты ID канала
        search_variants = [
            str(sender_chat_id),  # Полный ID: -1002242368150
            str(abs(sender_chat_id)),  # Без минуса: 1002242368150
            str(sender_chat_id)[4:] if len(str(abs(sender_chat_id))) > 10 else str(abs(sender_chat_id)),  # Убираем -100: 2242368150
        ]
        
        # Также попробуем найти по username, если канал связан с этим ID
        for variant in search_variants:
            logger.info(f"🔍 [FIND] Пробуем вариант ID: '{variant}'")
            result = await session.execute(
                select(Channel).where(Channel.name == variant)
            )
            channel = result.scalar_one_or_none()
            if channel:
                logger.info(f"✅ [FIND] Найден канал по варианту ID: {channel.name}")
                
                # Автоматически связываем канал с группой
                logger.info(f"🔗 [LINK] Автосвязывание канала {channel.name} с группой {group_id}")
                channel.discussion_group_id = group_id
                session.add(channel)
                await session.commit()
                logger.info(f"✅ [LINK] Канал {channel.name} успешно связан с группой {group_id}")
                
                return channel
    
    # Если не найден по ID, ищем среди всех каналов без определенной группы
    logger.info(f"🔍 [FIND] Ищем среди каналов без определенной группы...")
    all_channels = await session.execute(
        select(Channel).where(Channel.discussion_group_id.is_(None))
    )
    
    channels_without_group = list(all_channels.scalars())
    logger.info(f"📋 [FIND] Найдено каналов без группы: {len(channels_without_group)}")
    
    for channel in channels_without_group:
        logger.info(f"🔍 [FIND] Проверяем канал: {channel.name}")
        
        # Если у канала есть инвайт ссылка, пытаемся определить связь
        if channel.discussion_group_invite:
            logger.info(f"🔗 [FIND] Канал {channel.name} имеет инвайт ссылку, пробуем автосвязывание...")
            
            # Временно связываем с текущей группой для проверки
            # В реальной ситуации здесь можно было бы проверить через Telegram API
            # Но для упрощения просто связываем первый найденный канал
            logger.info(f"🔗 [LINK] Автосвязывание канала {channel.name} с группой {group_id}")
            channel.discussion_group_id = group_id
            session.add(channel)
            await session.commit()
            logger.info(f"✅ [LINK] Канал {channel.name} автоматически связан с группой {group_id}")
            
            return channel
    
    logger.warning(f"❌ [FIND] Канал не найден для группы {group_id}")
    logger.warning(f"💡 [HINT] Добавьте канал в систему или проверьте настройки группы обсуждений")
    return None

def ensure_unique_comments(comments: List[str], actual_count: int) -> List[str]:
    """
    УЛУЧШЕННАЯ функция для обеспечения уникальности комментариев.
    Перемешивает список и гарантирует разные комментарии для каждого аккаунта.
    """
    if not comments:
        logger.warning(f"⚠️ [UNIQUE] Список комментариев пустой")
        return []
    
    logger.info(f"🔀 [UNIQUE] Обеспечиваем уникальность комментариев...")
    logger.info(f"📊 [UNIQUE] Доступно комментариев: {len(comments)}, нужно: {actual_count}")
    
    # 1. Создаем копию списка для безопасности
    available_comments = comments.copy()
    
    # 2. ТЩАТЕЛЬНО перемешиваем список
    for _ in range(3):  # Перемешиваем 3 раза для лучшей рандомизации
        random.shuffle(available_comments)
    
    logger.info(f"🔀 [UNIQUE] Список перемешан")
    
    # 3. Если комментариев больше или равно нужному количеству - просто берем первые
    if len(available_comments) >= actual_count:
        selected_comments = available_comments[:actual_count]
        logger.info(f"✅ [UNIQUE] Выбрано {len(selected_comments)} уникальных комментариев")
        
        # Логируем первые символы для проверки уникальности
        for i, comment in enumerate(selected_comments):
            logger.debug(f"📝 [UNIQUE] Комментарий {i+1}: '{comment[:50]}...'")
        
        return selected_comments
    
    # 4. Если комментариев меньше чем нужно - дублируем с вариациями
    selected_comments = []
    variations_suffixes = [
        "",  # Оригинальный
        " 👍",
        " 🔥", 
        " ✨",
        " 💯",
        " 🎯",
        " 👏",
        " 💪"
    ]
    
    logger.info(f"⚠️ [UNIQUE] Комментариев меньше чем нужно, добавляем вариации...")
    
    comment_index = 0
    variation_index = 0
    
    for i in range(actual_count):
        # Берем базовый комментарий
        base_comment = available_comments[comment_index % len(available_comments)]
        
        # Добавляем вариацию (суффикс)
        if variation_index < len(variations_suffixes):
            final_comment = base_comment + variations_suffixes[variation_index]
        else:
            # Если суффиксы закончились, добавляем номер
            final_comment = base_comment + f" #{variation_index - len(variations_suffixes) + 1}"
        
        selected_comments.append(final_comment)
        
        logger.debug(f"📝 [UNIQUE] Комментарий {i+1}: '{final_comment[:50]}...'")
        
        # Переходим к следующему комментарию
        comment_index += 1
        
        # Если прошли все комментарии, переходим к следующей вариации
        if comment_index >= len(available_comments):
            comment_index = 0
            variation_index += 1
    
    logger.info(f"✅ [UNIQUE] Создано {len(selected_comments)} комментариев с вариациями")
    return selected_comments

# Новый фильтр: слушаем все сообщения в супергруппах
@router.message(F.chat.type == 'supergroup')
async def post_commenting(message: Message):
    logger.info(f"🔍 [DEBUG] Получено сообщение в супергруппе:")
    logger.info(f"  Chat ID: {message.chat.id}")
    logger.info(f"  Chat title: {message.chat.title}")
    logger.info(f"  Chat username: {message.chat.username}")
    logger.info(f"  From user: {message.from_user.id if message.from_user else None}")
    logger.info(f"  Sender chat: {message.sender_chat.id if message.sender_chat else None}")
    logger.info(f"  Message ID: {message.message_id}")
    logger.info(f"  Text: {message.text[:100] if message.text else 'No text'}")
    logger.info(f"  Caption: {message.caption[:100] if message.caption else 'No caption'}")
    
    # Проверяем, что это пост от канала в группу обсуждений
    if not message.sender_chat:
        logger.info(f"⏭️ [SKIP] Сообщение не от канала, пропускаем")
        return
    
    logger.info(f"🎯 [HANDLER] Обрабатываем пост от канала в группе обсуждений!")
    logger.info(f"  Группа: {message.chat.title} (ID: {message.chat.id})")
    logger.info(f"  Канал отправитель: {message.sender_chat.id}")
    logger.info(f"  Post ID: {message.message_id}")
    
    async with get_session() as session:
        try:
            # Находим канал по ID группы обсуждений с автосвязыванием
            channel = await find_channel_by_group_id(
                session, 
                message.chat.id, 
                message.sender_chat.id if message.sender_chat else None
            )
            
            if not channel:
                logger.warning(f"❌ [DB] Канал не найден для группы {message.chat.id}")
                logger.warning(f"    Убедитесь, что канал добавлен в систему")
                return
            
            logger.info(f"✅ [DB] Найден канал: {channel.name}")
            
            # Если у канала еще не определен ID группы, сохраняем его (уже сделано в find_channel_by_group_id)
            if not channel.discussion_group_id:
                channel.discussion_group_id = message.chat.id
                await session.commit()
                logger.info(f"💾 [DB] Сохранен ID группы для канала {channel.name}: {message.chat.id}")
            
            # Проверяем, стоит ли комментировать этот пост
            logger.info(f"🎲 [CHANCE] Проверяем шансы комментирования...")
            should_comment = await should_comment_on_post(session, channel, channel.name, message.message_id)
            logger.info(f"🎲 [CHANCE] Результат проверки: {should_comment}")
            
            if not should_comment:
                logger.info(f"⏭️ [SKIP] Пост пропущен по настройкам вероятности")
                return

            # Получаем активного агента
            logger.info(f"🤖 [AI] Ищем активного агента для канала {channel.id}")
            agent = await session.execute(
                select(AIAgent)
                .where(
                    AIAgent.channel_id == channel.id,
                    AIAgent.status == True
                )
            )
            agent = agent.scalar_one_or_none()

            if not agent:
                logger.warning(f"❌ [AI] Для канала {channel.name} не найден активный агент")
                return
            
            logger.info(f"✅ [AI] Найден активный агент: {agent.description} (API_ID: {agent.api_id})")

            # Получаем контент для ИИ
            content = message.text or message.caption or ""
            logger.info(f"📝 [CONTENT] Контент для ИИ: {content[:200]}...")

            # Получаем ответ от ИИ
            logger.info(f"🤖 [AI] Отправляем запрос к агенту...")
            try:
                response = await request(
                    agent_id=agent.api_id,
                    content=content
                )
                logger.info(f"✅ [AI] Получен ответ от ИИ: {len(response)} символов")
                logger.info(f"📄 [AI] Первые 300 символов ответа: {response[:300]}...")
            except Exception as e:
                logger.error(f"❌ [AI] Ошибка запроса к ИИ: {e}")
                return

            # Парсим комментарии
            comments = clean_comments(response)
            logger.info(f"💬 [PARSE] Распарсено комментариев: {len(comments)}")
            
            if not comments:
                logger.warning(f"⚠️ [PARSE] Не удалось получить комментарии из ответа ИИ")
                return

            # Рассчитываем количество комментариев
            comments_count = channel.comments_number
            comments_spread = channel.comments_number_range
            actual_count = max(1, min(
                comments_count + random.randint(-comments_spread, comments_spread),
                len(comments)
            ))
            logger.info(f"📊 [COUNT] Базовое количество: {comments_count}, разброс: {comments_spread}")
            logger.info(f"📊 [COUNT] Итоговое количество комментариев: {actual_count}")
            
            # УЛУЧШЕННЫЙ выбор уникальных комментариев
            selected_comments = ensure_unique_comments(comments, actual_count)
            logger.info(f"✅ [SELECT] Выбрано уникальных комментариев для отправки: {len(selected_comments)}")

            # Получаем случайные аккаунты для комментариев
            logger.info(f"👥 [ACCOUNTS] Ищем аккаунты для канала {channel.id}...")
            accounts = await get_random_accounts(session, actual_count, channel.id)
            logger.info(f"👥 [ACCOUNTS] Найдено аккаунтов: {len(accounts)}")
            
            if not accounts:
                logger.warning(f"❌ [ACCOUNTS] Нет доступных аккаунтов для комментариев")
                return

            # Парсим типы реакций для лайков
            reaction_types = [r.strip() for r in channel.likes_reaction_types.split(',') if r.strip()]
            logger.info(f"👍 [REACTIONS] Типы реакций: {reaction_types}")

            # Создаем задачи на комментирование
            comment_tasks = []
            
            for i, comment in enumerate(selected_comments):
                if i < len(accounts):
                    task = CommentTask(
                        account_session=accounts[i].session,
                        account_number=accounts[i].number,
                        channel=channel.name,
                        channel_id=channel.id,
                        post_id=message.message_id,
                        comment_text=comment,
                        delay=random.uniform(5, 15),
                        like_chance=channel.likes_on_posts_chance,
                        reaction_types=reaction_types,
                        # Данные для комментирования в группе
                        discussion_group_id=message.chat.id,  # ID группы обсуждений
                        sender_chat_id=message.sender_chat.id,  # ID канала-отправителя
                        invite_link=channel.discussion_group_invite,  # Инвайт ссылка для вступления
                        channel_username=channel.name  # Username канала для подписки - ИСПРАВЛЕНО!
                    )
                    comment_tasks.append(task)
                    logger.info(f"📝 [TASK] Создана задача для аккаунта {accounts[i].number}: {comment[:50]}...")
                    logger.info(f"🔍 [DEBUG] Channel username в задаче: {channel.name}")

            # Отправляем задачи комментирования в брокер
            try:
                logger.info(f"📨 [BROKER] Подключаемся к брокеру...")
                await broker.connect()
                logger.info(f"✅ [BROKER] Подключение успешно")

                logger.info(f"📨 [BROKER] Отправляем {len(comment_tasks)} задач в канал comment_tasks")
                result = await broker.publish(
                    message=CommentTaskMessage(data=comment_tasks),
                    channel="comment_tasks"
                )
                logger.info(f"✅ [BROKER] Задачи отправлены. Результат: {result}")

                # Создаем задачи на лайки комментариев других аккаунтов
                if channel.likes_on_comments_chance > 0:
                    logger.info(f"👍 [LIKES] Создаем задачи лайков комментариев (шанс: {channel.likes_on_comments_chance}%)")
                    like_tasks = await create_comment_like_tasks(
                        session, channel, channel.name, 
                        comment_tasks, reaction_types
                    )
                    
                    if like_tasks:
                        logger.info(f"📨 [BROKER] Отправляем {len(like_tasks)} задач лайков")
                        await broker.publish(
                            message=LikeCommentTaskMessage(data=like_tasks),
                            channel="like_comment_tasks"
                        )
                        logger.info(f"✅ [BROKER] Задачи лайков отправлены")
                    else:
                        logger.info(f"ℹ️ [LIKES] Задачи лайков не созданы")

                await broker.close()
                logger.info(f"🔌 [BROKER] Соединение закрыто")

                # Обновляем статистику активности
                logger.info(f"📊 [STATS] Обновляем статистику...")
                await update_post_activity(
                    session, channel.name, message.message_id, 
                    len(comment_tasks), 0  # лайки будут подсчитаны позже
                )
                await session.commit()
                logger.info(f"✅ [STATS] Статистика обновлена")

            except Exception as e:
                logger.error(f"❌ [BROKER] Ошибка при работе с брокером: {str(e)}")
                raise

            logger.info(f"🎉 [SUCCESS] Обработка поста завершена успешно!")

        except Exception as e:
            logger.error(f"❌ [ERROR] Ошибка в post_commenting: {str(e)}")
            await session.rollback()
            raise

async def create_comment_like_tasks(
    session, channel: Channel, channel_name: str, 
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
                    channel=channel_name,
                    comment_id=0,  # будет установлен после отправки комментария
                    target_comment_account=comment_task.account_number,
                    delay=like_delay,
                    reaction_types=reaction_types
                )
                like_tasks.append(like_task)
    
    return like_tasks
