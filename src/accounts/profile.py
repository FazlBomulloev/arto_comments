import asyncio
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.functions.account import UpdateProfileRequest
from src.cfg import config
from PIL import Image
import logging

logger = logging.getLogger(__name__)

async def update_telegram_profile(
        string_session: str,
        name: str = None,
        photo_path: str = None
) -> None:
    """
    Обновляет профиль Telegram аккаунта.
    
    Args:
        string_session: Строка сессии аккаунта
        name: Имя для установки (опционально, может быть None)
        photo_path: Путь к фото (опционально, может быть None)
    """
    client = TelegramClient(
        StringSession(string_session),
        api_id=config.API_ID,
        api_hash=config.API_HASH
    )

    try:
        await client.connect()
        logger.info(f"📱 Подключились к Telegram для обновления профиля")

        # 1. Обновляем имя (только если указано)
        if name:
            try:
                await client(UpdateProfileRequest(
                    first_name=name,
                    last_name=''
                ))
                logger.info(f"✅ Имя успешно изменено на: {name}")
            except Exception as e:
                logger.error(f"❌ Ошибка обновления имени: {e}")
                raise
        else:
            logger.info("ℹ️ Имя не указано, оставляем текущее имя без изменений")

        # 2. Обновляем фото (только если путь указан и файл существует)
        if photo_path:
            try:
                # Получаем абсолютный путь
                base_dir = Path(__file__).parent.parent.parent  # Поднимаемся до arto_comment_bot
                full_photo_path = base_dir / photo_path

                logger.info(f"🖼️ Проверяем фото по пути: {full_photo_path.absolute()}")

                # Проверяем существование файла
                if not full_photo_path.exists():
                    logger.warning(f"⚠️ Файл фото не найден: {full_photo_path.absolute()}")
                    logger.info(f"ℹ️ Продолжаем без обновления фото")
                    return  # Выходим, но без ошибки

                # Проверяем что файл является изображением
                try:
                    with Image.open(full_photo_path) as img:
                        img.verify()  # Проверка целостности изображения
                    logger.info("✅ Файл является валидным изображением")
                except Exception as e:
                    logger.warning(f"⚠️ Файл не является валидным изображением: {e}")
                    logger.info(f"ℹ️ Продолжаем без обновления фото")
                    return  # Выходим, но без ошибки

                # Удаляем старые фото
                try:
                    profile_photos = await client.get_profile_photos('me')
                    if profile_photos:
                        await client(DeletePhotosRequest(profile_photos))
                        logger.info("🗑️ Старые фото профиля удалены")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось удалить старые фото: {e}")
                    # Не критично, продолжаем

                # Загружаем новое фото
                try:
                    file = await client.upload_file(full_photo_path)
                    await client(UploadProfilePhotoRequest(file=file))
                    logger.info(f"✅ Фото успешно обновлено: {full_photo_path.name}")
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось загрузить фото: {e}")
                    # Не критично, профиль обновлен хотя бы именем

            except Exception as e:
                logger.warning(f"⚠️ Общая ошибка при работе с фото: {e}")
                # Не критично, имя уже обновлено
        else:
            logger.info("ℹ️ Путь к фото не указан, обновляем только имя")

        logger.info("🎉 Обновление профиля завершено")

    except Exception as e:
        logger.error(f"❌ Критическая ошибка при обновлении профиля: {str(e)}")
        raise  # Пробрасываем критические ошибки
    finally:
        try:
            await client.disconnect()
            logger.debug("📱 Отключились от Telegram")
        except:
            pass  # Игнорируем ошибки отключения
