import asyncio
from pathlib import Path
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.photos import UploadProfilePhotoRequest, DeletePhotosRequest
from telethon.tl.functions.account import UpdateProfileRequest
from src.cfg import config
from PIL import Image


async def update_telegram_profile(
        string_session: str,
        name: str,
        photo_path: str
) -> None:
    # Получаем абсолютный путь (правильный вариант)
    base_dir = Path(__file__).parent.parent.parent  # Поднимаемся до arto_comment_bot
    full_photo_path = base_dir / photo_path

    print(f"🔍 Проверяем путь: {full_photo_path.absolute()}")

    # Проверяем существование файла
    if not full_photo_path.exists():
        print(f"❌ Файл не найден: {full_photo_path.absolute()}")
        print("Проверьте структуру папок:")
        print((base_dir / "media").absolute())
        return

    # Проверяем что файл является изображением (современный способ)
    try:
        with Image.open(full_photo_path) as img:
            img.verify()  # Проверка целостности изображения
        print("✅ Файл является валидным изображением")
    except Exception as e:
        print(f"❌ Ошибка проверки изображения: {e}")
        return

    client = TelegramClient(
        StringSession(string_session),
        api_id=config.API_ID,
        api_hash=config.API_HASH
    )

    try:
        await client.connect()

        if name:
            await client(UpdateProfileRequest(
                first_name=name,
                last_name=''
            ))
            print(f"✅ Имя изменено на: {name}")

        # Удаляем старые фото
        profile_photos = await client.get_profile_photos('me')
        if profile_photos:
            await client(DeletePhotosRequest(profile_photos))

        # Загружаем новое фото
        file = await client.upload_file(full_photo_path)
        await client(UploadProfilePhotoRequest(
            file=file,
        ))
        print(f"✅ Фото обновлено: {full_photo_path}")

    except Exception as e:
        print(f"❌ Ошибка при обновлении профиля: {str(e)}")
    finally:
        await client.disconnect()