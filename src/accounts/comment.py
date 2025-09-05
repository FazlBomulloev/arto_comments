from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError
)
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetMessagesViewsRequest
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

        input_peer = await client.get_input_entity(message.chat.username)

        # 1. Просмотр поста
        try:
            await client(GetMessagesViewsRequest(
                peer=input_peer,
                id=[message.message_id],
                increment=True
            ))
            logger.debug(f"👀 Просмотр поста {message.message_id} в канале {message.chat.username}")
        except Exception as e:
            logger.warning(f"⚠️ Ошибка при просмотре поста: {type(e).__name__}: {e}")

        # 2. Случайная задержка перед комментарием (5-15 секунд)
        delay = random.uniform(5, 15)
        await asyncio.sleep(delay)

        # 3. Ставим лайк с заданным шансом
        if random.randint(1, 100) <= like_chance:
            try:
                if not available_reactions:
                    available_reactions = [
                        ReactionEmoji(emoticon="❤️"),
                        ReactionEmoji(emoticon="👍"),
                        ReactionEmoji(emoticon="🔥")
                    ]
                
                selected_reaction = random.choice(available_reactions)
                await client(SendReactionRequest(
                    peer=input_peer,
                    msg_id=message.message_id,
                    reaction=[selected_reaction]
                ))
                result["like_given"] = True
                logger.debug(f"👍 Поставлен лайк на пост {message.message_id}")
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при установке реакции: {type(e).__name__}: {e}")

        # 4. Отправляем комментарий
        try:
            sent_message = await client.send_message(
                entity=message.chat.username,
                reply_to=message.message_id,
                message=comment_text
            )
            result["comment_sent"] = True
            result["comment_id"] = sent_message.id
            result["success"] = True
            logger.info(f"✅ Комментарий отправлен в {message.chat.username}")

        except ChatWriteForbiddenError:
            result["error"] = "Нет прав на комментирование в канале"
            logger.warning("⛔ Нет прав на комментирование в канале")
        except ChatAdminRequiredError:
            result["error"] = "Требуются права администратора для комментирования"
            logger.warning("🔐 Требуются права администратора для комментирования")
        except ChannelPrivateError:
            result["error"] = "Канал приватный или нет доступа"
            logger.warning("🔒 Канал приватный или нет доступа")
        except FloodWaitError as e:
            result["error"] = f"Требуется ожидание {e.seconds} секунд"
            logger.warning(f"⏳ Требуется ожидание {e.seconds} секунд")

    except Exception as e:
        result["error"] = f"Общая ошибка: {type(e).__name__}: {e}"
        logger.error(f"⚠️ Ошибка при отправке комментария: {type(e).__name__}: {e}")
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