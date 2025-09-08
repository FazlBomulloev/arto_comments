from telethon.errors import (
    ChannelPrivateError,
    FloodWaitError,
    ChatAdminRequiredError,
    ChatWriteForbiddenError,
    UsernameNotOccupiedError,
    UsernameInvalidError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    UserAlreadyParticipantError
)
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.messages import GetMessagesViewsRequest, ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest
from src.cfg import config
from aiogram.types import Message
from telethon.errors import TypeNotFoundError
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji
import asyncio
import random
import logging
import re

logger = logging.getLogger(__name__)

def extract_invite_hash(invite_link: str) -> str:
    """Извлекает хеш из инвайт ссылки"""
    patterns = [
        r't\.me/\+([A-Za-z0-9_-]+)',
        r't\.me/joinchat/([A-Za-z0-9_-]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, invite_link)
        if match:
            return match.group(1)
    
    return None

async def join_channel_by_username(client, channel_username: str, account_number: str) -> bool:
    """Подписывается на канал по username"""
    try:
        logger.info(f"📺 [CHANNEL] [{account_number}] Подписываемся на канал: {channel_username}")
        
        # Убираем @ если есть
        clean_username = channel_username.lstrip('@')
        
        try:
            # Получаем сущность канала
            channel_entity = await client.get_entity(clean_username)
            
            # Подписываемся на канал
            await client(JoinChannelRequest(channel_entity))
            logger.info(f"✅ [CHANNEL] [{account_number}] Успешно подписались на канал {channel_username}")
            return True
            
        except UserAlreadyParticipantError:
            logger.info(f"ℹ️ [CHANNEL] [{account_number}] Уже подписан на канал {channel_username}")
            return True
            
        except UsernameNotOccupiedError:
            logger.error(f"❌ [CHANNEL] [{account_number}] Канал {channel_username} не существует")
            return False
            
        except UsernameInvalidError:
            logger.error(f"❌ [CHANNEL] [{account_number}] Некорректный username канала: {channel_username}")
            return False
            
        except ChannelPrivateError:
            logger.error(f"❌ [CHANNEL] [{account_number}] Канал {channel_username} приватный")
            return False
            
        except FloodWaitError as e:
            logger.warning(f"⏳ [CHANNEL] [{account_number}] Нужно подождать {e.seconds} секунд для подписки на канал")
            return False
            
        except Exception as e:
            logger.error(f"❌ [CHANNEL] [{account_number}] Ошибка подписки на канал: {type(e).__name__}: {e}")
            return False
            
    except Exception as e:
        logger.error(f"❌ [CHANNEL] [{account_number}] Критическая ошибка подписки на канал: {type(e).__name__}: {e}")
        return False

async def join_group_by_invite(client, invite_link: str, account_number: str) -> bool:
    """Вступает в группу по инвайт ссылке"""
    try:
        logger.info(f"👥 [GROUP] [{account_number}] Пытаемся вступить в группу по инвайт ссылке")
        
        # Извлекаем хеш из ссылки
        invite_hash = extract_invite_hash(invite_link)
        if not invite_hash:
            logger.error(f"❌ [GROUP] [{account_number}] Некорректная инвайт ссылка: {invite_link}")
            return False
        
        logger.info(f"🔑 [GROUP] [{account_number}] Извлечен хеш: {invite_hash}")
        
        # Вступаем в группу по хешу
        try:
            result = await client(ImportChatInviteRequest(invite_hash))
            logger.info(f"✅ [GROUP] [{account_number}] Успешно вступили в группу по инвайт ссылке")
            return True
            
        except UserAlreadyParticipantError:
            logger.info(f"ℹ️ [GROUP] [{account_number}] Уже участник группы")
            return True
            
        except InviteHashExpiredError:
            logger.error(f"❌ [GROUP] [{account_number}] Инвайт ссылка истекла")
            return False
            
        except InviteHashInvalidError:
            logger.error(f"❌ [GROUP] [{account_number}] Инвайт ссылка недействительна")
            return False
            
        except FloodWaitError as e:
            logger.warning(f"⏳ [GROUP] [{account_number}] Нужно подождать {e.seconds} секунд")
            return False
            
        except Exception as e:
            logger.error(f"❌ [GROUP] [{account_number}] Ошибка вступления в группу: {type(e).__name__}: {e}")
            return False
            
    except Exception as e:
        logger.error(f"❌ [GROUP] [{account_number}] Критическая ошибка: {type(e).__name__}: {e}")
        return False

async def post_comment_with_session(
        session_data: str,
        message: Message,
        comment_text: str,
        like_chance: int = 20,
        available_reactions: list = None,
        invite_link: str = None,
        account_number: str = "unknown",
        channel_username: str = None  # НОВЫЙ ПАРАМЕТР
) -> dict:
    """Функция для отправки комментариев к постам в группах с подпиской на канал и вступлением в группу"""
    client = None
    result = {
        "success": False,
        "comment_sent": False,
        "like_given": False,
        "comment_id": None,
        "error": None,
        "joined_group": False,
        "joined_channel": False
    }
    
    try:
        client = TelegramClient(
            StringSession(session_data),
            api_id=config.API_ID,
            api_hash=config.API_HASH
        )

        await client.connect()

        # Определяем целевую сущность для комментирования (группа обсуждений)
        target_entity = message.chat.id
        logger.info(f"📍 [TARGET] [{account_number}] Комментируем в группе: {target_entity}")
        
        # Логируем отладочную информацию комментария
        logger.info(f"🐛 [COMMENT DEBUG] [{account_number}] Отправка комментария:")
        logger.info(f"  Text: '{comment_text}'")
        logger.info(f"  Length: {len(comment_text)}")
        logger.info(f"  Target group: {target_entity}")
        logger.info(f"  Invite link: {invite_link}")
        logger.info(f"  Channel username: {channel_username}")

        # 1. Подписываемся на канал (если указан username)
        if channel_username:
            channel_join_success = await join_channel_by_username(client, channel_username, account_number)
            result["joined_channel"] = channel_join_success
            
            if channel_join_success:
                # Пауза после подписки на канал
                delay = random.uniform(2, 5)
                logger.info(f"⏱️ [CHANNEL] [{account_number}] Пауза после подписки на канал: {delay:.2f} сек")
                await asyncio.sleep(delay)
        else:
            logger.info(f"ℹ️ [CHANNEL] [{account_number}] Username канала не предоставлен")

        # 2. Вступаем в группу по инвайт ссылке (если предоставлена)
        if invite_link:
            group_join_success = await join_group_by_invite(client, invite_link, account_number)
            result["joined_group"] = group_join_success
            
            if group_join_success:
                # Пауза после вступления в группу
                delay = random.uniform(3, 8)
                logger.info(f"⏱️ [GROUP] [{account_number}] Пауза после вступления в группу: {delay:.2f} сек")
                await asyncio.sleep(delay)
            else:
                logger.warning(f"⚠️ [GROUP] [{account_number}] Не удалось вступить в группу, продолжаем без вступления")
        else:
            logger.info(f"ℹ️ [GROUP] [{account_number}] Инвайт ссылка не предоставлена")

        # 3. Просмотр поста
        try:
            # Пытаемся просматривать через группу вместо канала для стабильности
            view_peer = await client.get_input_entity(target_entity)
            logger.info(f"👀 [VIEW] [{account_number}] Просматриваем через группу: {target_entity}")
                
            await client(GetMessagesViewsRequest(
                peer=view_peer,
                id=[message.message_id],
                increment=True
            ))
            logger.debug(f"✅ [VIEW] [{account_number}] Просмотр поста {message.message_id} выполнен")
        except Exception as e:
            # Не критично если просмотр не удался
            logger.warning(f"⚠️ [VIEW] [{account_number}] Ошибка при просмотре поста: {type(e).__name__}")
            # Продолжаем выполнение без просмотра

        # 4. Случайная задержка перед комментарием
        delay = random.uniform(10, 25)
        logger.info(f"⏱️ [DELAY] [{account_number}] Ждем {delay:.2f} секунд перед комментированием")
        await asyncio.sleep(delay)

        # 5. Ставим лайк с заданным шансом
        if random.randint(1, 100) <= like_chance:
            try:
                if not available_reactions:
                    available_reactions = [
                        ReactionEmoji(emoticon="❤️"),
                        ReactionEmoji(emoticon="👍"),
                        ReactionEmoji(emoticon="🔥")
                    ]
                
                selected_reaction = random.choice(available_reactions)
                
                # Для лайка используем группу вместо канала для стабильности
                reaction_peer = await client.get_input_entity(target_entity)
                    
                await client(SendReactionRequest(
                    peer=reaction_peer,
                    msg_id=message.message_id,
                    reaction=[selected_reaction]
                ))
                result["like_given"] = True
                logger.debug(f"👍 [LIKE] [{account_number}] Поставлен лайк на пост {message.message_id}")
            except Exception as e:
                # Не критично если лайк не удался
                logger.warning(f"⚠️ [LIKE] [{account_number}] Ошибка при установке реакции: {type(e).__name__}")
                # Продолжаем выполнение без лайка

        # 6. Отправляем комментарий в группу обсуждений
        logger.info(f"💬 [COMMENT] [{account_number}] Отправляем комментарий в группу {target_entity}")
        
        try:
            # Добавляем небольшую задержку для стабилизации соединения
            await asyncio.sleep(random.uniform(1, 3))
            
            sent_message = await client.send_message(
                entity=target_entity,  # Комментируем в группе обсуждений
                reply_to=message.message_id,
                message=comment_text
            )
            result["comment_sent"] = True
            result["comment_id"] = sent_message.id
            result["success"] = True
            logger.info(f"✅ [COMMENT] [{account_number}] Комментарий отправлен (ID: {sent_message.id})")

        except TypeNotFoundError as e:
            logger.warning(f"⚠️ [COMMENT] [{account_number}] Ошибка схемы Telethon, переподключаемся...")
            try:
                await client.disconnect()
                await asyncio.sleep(2)
                
                client = TelegramClient(StringSession(session_data), api_id=config.API_ID, api_hash=config.API_HASH)
                await client.connect()
                
                sent_message = await client.send_message(entity=target_entity, reply_to=message.message_id, message=comment_text)
                result["comment_sent"] = True
                result["comment_id"] = sent_message.id
                result["success"] = True
                logger.info(f"✅ [COMMENT] [{account_number}] Комментарий отправлен после переподключения (ID: {sent_message.id})")
            except Exception as retry_error:
                result["error"] = f"Ошибка схемы Telethon: {str(retry_error)}"
                logger.error(f"❌ [COMMENT] [{account_number}] Повторная попытка не удалась: {retry_error}")
        
        except ChatWriteForbiddenError:
            result["error"] = "Нет прав на комментирование в группе"
            logger.warning(f"⛔ [COMMENT] [{account_number}] Нет прав на комментирование")
        except ChatAdminRequiredError:
            result["error"] = "Требуются права администратора для комментирования"
            logger.warning(f"🔐 [COMMENT] [{account_number}] Требуются права администратора")
        except ChannelPrivateError:
            result["error"] = "Группа приватная или нет доступа"
            logger.warning(f"🔒 [COMMENT] [{account_number}] Группа приватная или нет доступа")
        except FloodWaitError as e:
            result["error"] = f"Требуется ожидание {e.seconds} секунд"
            logger.warning(f"⏳ [COMMENT] [{account_number}] Требуется ожидание {e.seconds} секунд")
            
        except Exception as e:
            # Для TypeNotFoundError и других проблем с протоколом
            error_msg = str(e)
            if "TypeNotFoundError" in error_msg or "Constructor ID" in error_msg:
                result["error"] = "Ошибка протокола Telegram, пропускаем"
                logger.warning(f"🔧 [COMMENT] [{account_number}] Ошибка протокола Telegram: {type(e).__name__}")
            else:
                result["error"] = f"Ошибка отправки: {type(e).__name__}"
                logger.warning(f"⚠️ [COMMENT] [{account_number}] Ошибка отправки комментария: {type(e).__name__}: {str(e)[:100]}")

    except Exception as e:
        result["error"] = f"Общая ошибка: {type(e).__name__}: {e}"
        logger.error(f"⚠️ [COMMENT] [{account_number}] Общая ошибка при отправке комментария: {type(e).__name__}: {str(e)[:100]}")
    finally:
        if client:
            try:
                await client.disconnect()
            except:
                pass  # Игнорируем ошибки отключения
    
    return result

async def like_comment_with_session(
        session_data: str,
        group_id: int,
        comment_id: int,
        available_reactions: list = None,
        account_number: str = "unknown"
) -> bool:
    """Функция для лайка комментария в группе обсуждений"""
    client = None
    try:
        client = TelegramClient(
            StringSession(session_data),
            api_id=config.API_ID,
            api_hash=config.API_HASH
        )

        await client.connect()
        
        # Получаем сущность группы для лайка
        try:
            input_peer = await client.get_input_entity(group_id)
            logger.info(f"👍 [LIKE] [{account_number}] Используем группу для лайка: {group_id}")
        except Exception as e:
            logger.error(f"❌ [LIKE] [{account_number}] Ошибка получения сущности {group_id}: {e}")
            return False

        # Задержка перед лайком
        delay = random.uniform(5, 15)
        logger.info(f"⏱️ [LIKE] [{account_number}] Задержка перед лайком: {delay:.2f} сек")
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
        
        logger.info(f"👍 [LIKE] [{account_number}] Лайк поставлен на комментарий {comment_id} в группе {group_id}")
        return True

    except Exception as e:
        logger.error(f"⚠️ [LIKE] [{account_number}] Ошибка при лайке комментария {comment_id}: {type(e).__name__}: {e}")
        return False
    finally:
        if client:
            try:
                await client.disconnect()
            except:
                pass