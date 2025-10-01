from opentele.td import TDesktop
from opentele.api import API, UseCurrentSession
import asyncio, os, shutil, logging
from src.cfg import config
from pathlib import Path
from telethon import functions, events, types, errors
from telethon.sync import TelegramClient
from telethon import functions
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneNumberInvalidError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    FloodWaitError,
    AuthKeyInvalidError,
    AccessTokenExpiredError,
    ApiIdInvalidError,
    ApiIdPublishedFloodError,
    RPCError,
    AuthKeyError,
    ChannelPrivateError
)

logger = logging.getLogger(__name__)

async def session_create(tdata_path: Path) -> str:
    # Проверяем существует ли папка tdata
    if not tdata_path.exists() or not tdata_path.is_dir():
        logger.error(f"Папка tdata не существует: {tdata_path}")
        return None

    # Проверяем есть ли файлы в tdata
    if not any(tdata_path.glob('*')):
        logger.error(f"Папка tdata пуста: {tdata_path}")
        return None

    client = None
    try:
        # Создаем временный путь для сессии
        temp_session_path = tdata_path.parent / "temp.session"

        # Создаем TDesktop клиент
        tdesk = TDesktop(tdata_path)

        if not tdesk.accounts:
            logger.error(f"Нет валидных аккаунтов в tdata: {tdata_path}")
            return None
        # Конвертируем в Telethon клиент
        client = await tdesk.ToTelethon(
            session=str(temp_session_path),
            flag=UseCurrentSession)

        await client.disconnect()

        client=TelegramClient(api_hash=config.API_HASH, api_id=config.API_ID, session=temp_session_path)
        session_string = StringSession.save(client.session)

        logger.info(f"Успешно создана сессия для аккаунта в {tdata_path}")
        return session_string

    except Exception as e:
        logger.error(f"Ошибка при создании сессии для {tdata_path}: {str(e)}")
        return None

async def is_account_valid(
    session_data: str,  # session_data из БД (сериализованная сессия)
    phone: str          # Номер телефона (для идентификации)
) -> bool:
    """
    Упрощенная валидация аккаунта - проверяем только возможность подключения
    """
    client = None
    try:
        # Подключаемся к клиенту
        client = TelegramClient(
            session=StringSession(session_data), 
            api_id=config.API_ID,
            api_hash=config.API_HASH
        )
        await client.connect()

        try:
            # Простая проверка - получаем информацию о себе
            me = await client.get_me()
            if me:  # Если получили данные о себе - аккаунт рабочий
                logger.info(f"✅ Аккаунт {phone} прошел валидацию (ID: {me.id})")
                return True
            else:
                logger.warning(f"❌ Не удалось получить данные о себе для {phone}")
                return False
                
        except Exception as e:
            # Логируем ошибку, но не делаем аккаунт невалидным из-за разовых проблем
            logger.warning(f"⚠️ Ошибка при проверке аккаунта {phone}: {type(e).__name__}: {e}")
            # Если смогли подключиться, считаем аккаунт валидным
            return True
            
    except (AuthKeyError, AuthKeyInvalidError, AccessTokenExpiredError) as e:
        # Критические ошибки авторизации - аккаунт невалидный
        logger.error(f"❌ Критическая ошибка авторизации {phone}: {type(e).__name__}: {e}")
        return False
        
    except (SessionPasswordNeededError, FloodWaitError) as e:
        # 2FA или флуд - не критично, аккаунт может быть рабочим
        logger.warning(f"⚠️ Временная проблема с аккаунтом {phone}: {type(e).__name__}: {e}")
        return True  # Считаем валидным, проблему можно решить позже
        
    except Exception as e:
        # Прочие ошибки - логируем, но не отбрасываем аккаунт
        logger.warning(f"⚠️ Неизвестная ошибка для {phone}: {type(e).__name__}: {e}")
        return True  # Мягкая валидация - даем аккаунту шанс
        
    finally:
        if client:
            try:
                await client.disconnect()
            except:
                pass  # Игнорируем ошибки отключения
