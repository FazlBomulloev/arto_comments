from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError
)
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetMessagesViewsRequest
from telethon.tl.functions.channels import JoinChannelRequest
from src.cfg import config
from aiogram.types import Message
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji
import asyncio
import random
import logging

logger = logging.getLogger(__name__)

async def post_comment_with_session(
        session_data: str,
        message: Message,
        comment_text: str,
        like_chance: int = 20,
        available_reactions: list = None
) -> dict:
    """Функция для отправки комментариев к постам в каналах с просмотром и реакцией"""
    client = None
    result = {
        "success": False,
        "comment_sent": False,
        "like_given": False,
        "comment_id": None,
        "error": None
    }
    
    try:
        client = TelegramClient(
            StringSession(session_data),
            api_id=config.API_ID,
            api_hash=config.API_HASH
        )

        await client.connect()

        # Определяем целевую сущность для комментирования
        # Используем ID из message.chat (где нужно комментировать)
        target_entity = message.chat.id
        logger.info(f"📍 [TARGET] Комментируем в: {target_entity} (тип: {message.chat.type})")
        
        # Логируем отладочную информацию комментария
        logger.info(f"🐛 [COMMENT DEBUG] Отправка комментария:")
        logger.info(f"  Text: '{comment_text}'")
        logger.info(f"  Length: {len(comment_text)}")
        logger.info(f"  Repr: {repr(comment_text)}")
        logger.info(f"  Target entity: {target_entity}")

        # 1. Пытаемся подписаться на группу/канал
        try:
            logger.info(f"👥 [JOIN] Проверяем подписку на {target_entity}")
            entity = await client.get_entity(target_entity)
            
            # Пытаемся присоединиться (если уже участник, ошибки не будет)
            try:
                await client(JoinChannelRequest(entity))
                logger.info(f"✅ [JOIN] Присоединились/уже участник {target_entity}")
                await asyncio.sleep(random.uniform(1, 3))  # Небольшая пауза
            except Exception as join_error:
                # Возможно уже участник или другая ошибка
                logger.info(f"ℹ️ [JOIN] Результат присоединения: {join_error}")

        except Exception as e:
            logger.warning(f"⚠️ [JOIN] Ошибка при работе с подпиской: {e}")

        # 2. Просмотр поста
        try:
            # Для просмотра используем отправителя сообщения (канал) если есть
            if hasattr(message, 'sender_chat') and message.sender_chat:
                view_peer = await client.get_input_entity(message.sender_chat.id)
                logger.info(f"👀 [VIEW] Просматриваем через канал-отправитель: {message.sender_chat.id}")
            else:
                view_peer = await client.get_input_entity(target_entity)
                logger.info(f"👀 [VIEW] Просматриваем через текущий чат: {target_entity}")
                
            await client(GetMessagesViewsRequest(
                peer=view_peer,
                id=[message.message_id],
                increment=True
            ))
            logger.debug(f"✅ [VIEW] Просмотр поста {message.message_id} выполнен")
        except Exception as e:
            logger.warning(f"⚠️ [VIEW] Ошибка при просмотре поста: {type(e).__name__}: {e}")

        # 3. Случайная задержка перед комментарием
        delay = random.uniform(5, 15)
        logger.info(f"⏱️ [DELAY] Ждем {delay:.2f} секунд перед комментированием")
        await asyncio.sleep(delay)

        # 4. Ставим лайк с заданным шансом
        if random.randint(1, 100) <= like_chance:
            try:
                if not available_reactions:
                    available_reactions = [
                        ReactionEmoji(emoticon="❤️"),
                        ReactionEmoji(emoticon="👍"),
                        ReactionEmoji(emoticon="🔥")
                    ]
                
                selected_reaction = random.choice(available_reactions)
                
                # Для лайка используем тот же peer, что и для просмотра
                if hasattr(message, 'sender_chat') and message.sender_chat:
                    reaction_peer = await client.get_input_entity(message.sender_chat.id)
                else:
                    reaction_peer = await client.get_input_entity(target_entity)
                    
                await client(SendReactionRequest(
                    peer=reaction_peer,
                    msg_id=message.message_id,
                    reaction=[selected_reaction]
                ))
                result["like_given"] = True
                logger.debug(f"👍 [LIKE] Поставлен лайк на пост {message.message_id}")
            except Exception as e:
                logger.warning(f"⚠️ [LIKE] Ошибка при установке реакции: {type(e).__name__}: {e}")

        # 5. Отправляем комментарий
        logger.info(f"💬 [COMMENT] Отправляем комментарий в {target_entity}")
        
        try:
            sent_message = await client.send_message(
                entity=target_entity,  # Комментируем там, где получили сообщение
                reply_to=message.message_id,
                message=comment_text
            )
            result["comment_sent"] = True
            result["comment_id"] = sent_message.id
            result["success"] = True
            logger.info(f"✅ [COMMENT] Комментарий отправлен (ID: {sent_message.id})")

        except ChatWriteForbiddenError:
            result["error"] = "Нет прав на комментирование в канале"
            logger.warning("⛔ [COMMENT] Нет прав на комментирование")
        except ChatAdminRequiredError:
            result["error"] = "Требуются права администратора для комментирования"
            logger.warning("🔐 [COMMENT] Требуются права администратора для комментирования")
        except ChannelPrivateError:
            result["error"] = "Канал приватный или нет доступа"
            logger.warning("🔒 [COMMENT] Канал приватный или нет доступа")
        except FloodWaitError as e:
            result["error"] = f"Требуется ожидание {e.seconds} секунд"
            logger.warning(f"⏳ [COMMENT] Требуется ожидание {e.seconds} секунд")

    except Exception as e:
        result["error"] = f"Общая ошибка: {type(e).__name__}: {e}"
        logger.error(f"⚠️ [COMMENT] Ошибка при отправке комментария: {type(e).__name__}: {e}")
    finally:
        if client:
            await client.disconnect()
    
    return result

async def like_comment_with_session(
        session_data: str,
        channel_username: str,
        comment_id: int,
        available_reactions: list = None
) -> bool:
    """Функция для лайка комментария"""
    client = None
    try:
        client = TelegramClient(
            StringSession(session_data),
            api_id=config.API_ID,
            api_hash=config.API_HASH
        )

        await client.connect()
        input_peer = await client.get_input_entity(channel_username)

        # Задержка перед лайком
        delay = random.uniform(3, 10)
        await asyncio.sleep(delay)

        if not available_reactions:
            available_reactions = [
                ReactionEmoji(emoticon="❤️"),
                ReactionEmoji(emoticon="👍"),
                ReactionEmoji(emoticon="🔥")
            ]

        selected_reaction = random.choice(available_reactions)
        await client(SendReactionRequest(
            peer=input_peer,
            msg_id=comment_id,
            reaction=[selected_reaction]
        ))
        
        logger.info(f"👍 Лайк поставлен на комментарий {comment_id} в {channel_username}")
        return True

    except Exception as e:
        logger.error(f"⚠️ Ошибка при лайке комментария {comment_id}: {type(e).__name__}: {e}")
        return False
    finally:
        if client:
            await client.disconnect()