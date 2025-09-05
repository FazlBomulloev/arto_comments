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
    try:
        # Подключаемся к клиенту
        client = TelegramClient(session=StringSession(session_data), api_id=config.API_ID,api_hash=config.API_HASH)
        await client.connect()

        # Проверяем аккаунт через get.me
        try:

            entity=await client.get_entity('t.me/awattitest')
            x=bool(entity)
            me = await client.get_me()
            if me:  # Аккаунт рабочий
                return True
        except (ChannelPrivateError, AuthKeyError, RPCError) as e:
            print(f"Ошибка проверки аккаунта {phone}: {e}")
            return False
        finally:
            await client.disconnect()
    except (SessionPasswordNeededError, FloodWaitError) as e:
        print(f"Аккаунт {phone} требует 2FA или FloodWait: {e}")
        return False
    except Exception as e:
        print(f"Неизвестная ошибка у {phone}: {e}")
        return False
    finally:
        try:
            await client.disconnect()
        except:
            pass
