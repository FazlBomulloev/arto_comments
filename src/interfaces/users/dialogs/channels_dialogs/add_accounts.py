from pathlib import Path
import zipfile
import time
from aiogram.types import Message, CallbackQuery, ContentType
from aiogram_dialog.widgets.kbd import Button, Back, Cancel, Select, Group, Row, SwitchTo
from aiogram_dialog.widgets.input import MessageInput
from aiogram_dialog import Dialog, Window, DialogManager, ShowMode
from aiogram_dialog.widgets.text import Const, Format

from src.accounts.session import session_create
from src.interfaces.users.dialogs.channels_dialogs.utils import on_back_channel_menu
from src.interfaces.users.states import accounts,channels
from sqlalchemy import select
from src.db.models import Channel, Account, AIAgent
from src.db.pool_manager import get_session
import logging, random
import aiofiles
import aiofiles.os
import asyncio
from src.accounts.session import is_account_valid
from src.accounts.profile import update_telegram_profile

logger = logging.getLogger(__name__)

async def on_ok_button(c: CallbackQuery, button: Button, manager: DialogManager):
    """Обработчик кнопки OK - возвращает в меню канала"""
    channel_id = int(manager.start_data.get('channel_id'))
    await manager.start(
        state=channels.channel_menu,
        data={"channel_id": channel_id},
        show_mode=ShowMode.EDIT
    )


async def get_random_photo(channel_id: int, gender: str) -> Path:
    """Получает случайное фото из папки и удаляет его после выбора"""
    base_path = Path("media") / "accounts" / str(channel_id) / gender
    try:
        photos = [f for f in base_path.iterdir() if f.is_file() and f.suffix.lower() in ('.jpg', '.jpeg', '.png')]
        if not photos:
            raise ValueError(f"No photos found in {base_path}")

        selected_photo = random.choice(photos)
        return selected_photo
    except Exception as e:
        logger.error(f"Error getting photo for {gender}: {e}")
        raise


async def remove_used_photo(photo_path: Path) -> None:
    """Удаляет использованное фото"""
    try:
        await aiofiles.os.remove(photo_path)
        logger.debug(f"Removed used photo: {photo_path}")
    except Exception as e:
        logger.error(f"Error removing photo {photo_path}: {e}")


async def get_and_remove_name(channel_id: int, gender: str, session) -> str:
    """Получает случайное имя из списка в БД и удаляет его из доступных"""
    try:
        channel = await session.get(Channel, channel_id)
        if not channel:
            raise ValueError("Channel not found")

        # Получаем список имен из БД
        name_list = getattr(channel, f"acc_{gender}_name_list", "")
        names = [n.strip() for n in name_list.split('\n') if n.strip()]

        if not names:
            raise ValueError(f"No names available for {gender}")

        # Выбираем случайное имя
        selected_name = random.choice(names)

        # Удаляем выбранное имя из списка в БД
        updated_names = [n for n in names if n != selected_name]
        setattr(channel, f"acc_{gender}_name_list", '\n'.join(updated_names))

        await session.commit()
        return selected_name
    except Exception as e:
        logger.error(f"Error getting name for {gender}: {e}")
        raise


async def assign_profile_data(account: Account, channel_id: int, session):
    """Назначает аккаунту пол, имя и фото, обновляет профиль в Telegram"""
    try:
        # Определяем пол (50/50)
        gender = 'male' if random.random() < 0.5 else 'female'

        # Получаем имя (удаляется из списка в БД)
        name = await get_and_remove_name(channel_id, gender, session)

        # Получаем случайное фото
        photo_path = await get_random_photo(channel_id, gender)

        # Обновляем профиль в Telegram
        await update_telegram_profile(
            string_session=account.session,
            name=name,
            photo_path=str(photo_path)
        )

        # Удаляем использованное фото
        await remove_used_photo(photo_path)

        # Сохраняем данные в аккаун

        return True
    except Exception as e:
        logger.error(f"Error assigning profile data for {account.number}: {e}")
        return False

async def show_results(dialog_manager: DialogManager, **kwargs):
    """Геттер для окна с результатами"""
    return {
        "total": dialog_manager.dialog_data.get('total_accounts', 0),
        "added": dialog_manager.dialog_data.get('added_accounts', 0),
        "skipped": dialog_manager.dialog_data.get('skipped_accounts', 0)
    }

async def handle_zip_file(message: Message, message_input: MessageInput, manager: DialogManager):
    if not message.document or not message.document.file_name.lower().endswith('.zip'):
        await message.answer("❌ Отправьте файл в формате ZIP")
        return

    try:
        file_id = message.document.file_id
        file = await message.bot.get_file(file_id)

        UPLOAD_DIR = Path('downloads')
        await aiofiles.os.makedirs(UPLOAD_DIR, exist_ok=True)
        temp_zip_path = UPLOAD_DIR / f"temp_{int(time.time())}.zip"

        file_bytes = await message.bot.download(file)
        file_bytes = file_bytes.getvalue()  # Convert BytesIO to bytes

        # Write bytes to file
        async with aiofiles.open(temp_zip_path, 'wb') as f:
            await f.write(file_bytes)
        # Verify it's actually a ZIP file
        try:
            with zipfile.ZipFile(temp_zip_path, 'r') as test_zip:
                if not test_zip.testzip():
                    manager.dialog_data['zip_path'] = str(temp_zip_path)
                    manager.dialog_data['message_to_delete'] = message.message_id
                    await manager.switch_to(accounts.processing_zip, show_mode=ShowMode.EDIT)
                    test_zip.close()
                    await process_zip_file(manager)
                else:
                    await message.answer("❌ Файл поврежден или не является ZIP архивом")
                    await aiofiles.os.remove(temp_zip_path)
        except zipfile.BadZipFile:
            await message.answer("❌ Файл не является ZIP архивом")
            await aiofiles.os.remove(temp_zip_path)

    except Exception as e:
        logger.error(f"Ошибка загрузки файла: {e}", exc_info=True)
        await message.answer("❌ Ошибка при загрузке файла")
        if 'temp_zip_path' in locals():
            await aiofiles.os.remove(temp_zip_path)


async def process_zip_file(manager: DialogManager):
    zip_path = manager.dialog_data.get('zip_path')
    channel_id = manager.start_data.get('channel_id')

    if not zip_path or not channel_id:
        await manager.event.answer("Ошибка обработки файла", show_alert=True)
        await manager.done()
        return

    try:
        extract_path = Path('accounts') / str(channel_id)
        await aiofiles.os.makedirs(extract_path, exist_ok=True)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            all_items = zip_ref.namelist()
            root_folders = {item.split('/')[0] for item in all_items if '/' in item}

            if not root_folders:
                await manager.event.answer("❌ В архиве нет папок с аккаунтами")
                return

            zip_ref.extractall(path=extract_path)

        added_accounts = 0
        skipped_accounts = 0
        total_accounts = len(root_folders)

        async with get_session() as session:
            channel = await session.get(Channel, channel_id)
            if not channel:
                await manager.event.answer("Канал не найден")
                return

            for phone in root_folders:
                account_path = extract_path / phone

                if not account_path.is_dir():
                    skipped_accounts += 1
                    continue

                existing_account = await session.execute(
                    select(Account).where(Account.number == phone)
                )
                existing_account = existing_account.scalar_one_or_none()

                if existing_account:
                    skipped_accounts += 1
                    continue

                tdata_path = account_path / 'tdata'
                if not tdata_path.exists():
                    skipped_accounts += 1
                    continue

                try:
                    session_data = await session_create(Path(tdata_path))
                    await asyncio.sleep(1)
                    x = await is_account_valid(session_data, phone)
                    if x:
                        new_account = Account(
                            number=phone,
                            session=session_data,
                            channel_id=channel_id,
                            status="active"
                        )
                        session.add(new_account)
                        await session.flush()

                        # Назначаем профильные данные
                        success = await assign_profile_data(new_account, channel_id, session)
                        if not success:
                            logger.warning(f"Не удалось назначить профиль для {phone}")
                            skipped_accounts += 1
                            continue

                        added_accounts += 1
                        logger.info(f"[{phone}] УСПЕШНО ЗАГРУЖЕН!")
                    else:
                        skipped_accounts += 1
                except Exception as e:
                    logger.error(f"Ошибка создания сессии для {phone}: {e}")
                    skipped_accounts += 1

            await session.commit()

        manager.dialog_data.update({
            'total_accounts': total_accounts,
            'added_accounts': added_accounts,
            'skipped_accounts': skipped_accounts
        })

        # Ensure the file is closed before deletion
        attempts = 0
        while attempts < 3:
            try:
                await aiofiles.os.remove(zip_path)
                break
            except PermissionError:
                attempts += 1
                if attempts == 3:
                    logger.warning(f"Не удалось удалить файл {zip_path} после 3 попыток")
                else:
                    await asyncio.sleep(1)

        try:
            await manager.event.bot.delete_message(
                chat_id=manager.event.from_user.id,
                message_id=manager.dialog_data['message_to_delete']
            )
        except Exception:
            pass

        await manager.switch_to(accounts.show_results, show_mode=ShowMode.EDIT)

    except Exception as e:
        logger.error(f"Ошибка обработки ZIP: {e}", exc_info=True)
        await manager.event.answer("❌ Ошибка при обработке архива")
        await manager.done()

accounts_dialog = Dialog(
    Window(
        Const("Отправьте файл в формате <b>.zip</b> с аккаунтами:"),
        MessageInput(handle_zip_file, content_types=[ContentType.DOCUMENT]),
        Button(Const("Отмена"), on_click=on_back_channel_menu, id='zip_back'),
        state=accounts.wait_zip_file,
    ),
    Window(
        Const("Обработка архива..."),
        state=accounts.processing_zip,
    ),
    Window(
        Format(
            "📊 Результат обработки:\n\n"
            "• Всего аккаунтов: {total}\n"
            "• Добавлено новых: {added}\n"
            "• Пропущено: {skipped}"
        ),
        Row(
            Button(Const("ОК"), id="ok_button", on_click=on_ok_button),
        ),
        state=accounts.show_results,
        getter=show_results
    )
)