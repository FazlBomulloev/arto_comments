from aiogram_dialog import Dialog, Window, DialogManager, ShowMode
from aiogram_dialog.widgets.kbd import Button, Select, Group, Back, Url,SwitchTo, Row
from aiogram_dialog.widgets.text import Const, Format
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, delete, func
from aiogram_dialog.widgets.input import TextInput, MessageInput
from aiogram.types import Message, InputFile

from src.db import get_session, Account
from src.db.models import Channel, AIAgent
from ..states import channels,menu,agents,accounts,settings
from .utils import on_click_back_main_menu

import zipfile
import os
from pathlib import Path
import shutil
import re
import logging

logger = logging.getLogger(__name__)

# Главное меню управления каналами
async def channels_menu_getter(dialog_manager: DialogManager, **kwargs):
    async with get_session() as session:
        result = await session.execute(select(Channel))
        channels = result.scalars().all()

    return {
        "channels_menu": channels,
    }


# Меню конкретного канала
async def channel_actions_getter(dialog_manager: DialogManager, **kwargs):
    channel_id = dialog_manager.dialog_data.get("channel_id")
    if not channel_id:
        channel_id = dialog_manager.start_data.get("channel_id")
        if channel_id:
            dialog_manager.dialog_data["channel_id"] = channel_id
    async with get_session() as session:
        channel = await session.get(Channel, channel_id)
        # Получаем активного агента
        active_agent = await session.execute(
            select(AIAgent).where(
                AIAgent.channel_id == int(channel_id),
                AIAgent.status == True
            )
        )
        active_agent = active_agent.scalar_one_or_none()

        # Формируем список агентов с меткой статуса
        all_agents = await session.execute(select(AIAgent).where(AIAgent.channel_id == int(channel_id)))
        agents_with_status = []
        for agent in all_agents.scalars():
            status = "✅" if active_agent and agent.agent_id == active_agent.agent_id else ""
            agents_with_status.append({
                "agent": agent,
                "status": status
            })

    return {
        "channel_name": channel.name,
        "discussion_group_invite": channel.discussion_group_invite,
        "discussion_group_id": channel.discussion_group_id or "Не определен",
        "agents": agents_with_status,
        "active_agent": active_agent.description if active_agent else "Не выбран",
        
        # Параметры комментирования
        "comments_chance": channel.comments_chance,
        "comments_number": channel.comments_number,
        "comments_number_range": channel.comments_number_range,
        
        # Новые параметры выбора постов
        "post_selection_chance": channel.post_selection_chance,
        "post_min_interval": channel.post_min_interval,
        "post_max_interval": channel.post_max_interval,
        
        # Параметры лайков
        "likes_on_posts_chance": channel.likes_on_posts_chance,
        "likes_on_comments_chance": channel.likes_on_comments_chance,
        "likes_reaction_types": channel.likes_reaction_types.replace(',', ', ')
    }


# Геттер для окна подтверждения добавления канала
async def confirm_channel_getter(dialog_manager: DialogManager, **kwargs):
    channel_username = dialog_manager.dialog_data.get('channel_username', '')
    invite_link = dialog_manager.dialog_data.get('invite_link', '')
    return {
        "channel_username": channel_username,
        "invite_link": invite_link,
        "channel_url": f"https://t.me/{channel_username.lstrip('@')}" if channel_username else ""
    }

# НОВЫЕ ФУНКЦИИ ДЛЯ ПЕРЕНОСА АККАУНТОВ

# Геттер для выбора канала назначения
async def get_transfer_channels(dialog_manager: DialogManager, **kwargs):
    current_channel_id = dialog_manager.dialog_data.get("channel_id")
    
    async with get_session() as session:
        # Получаем все каналы кроме текущего
        result = await session.execute(
            select(Channel).where(Channel.id != current_channel_id)
        )
        channels = result.scalars().all()
    
    return {
        "channels": channels,
        "current_channel_id": current_channel_id
    }

# Геттер для подтверждения переноса
async def get_transfer_confirmation(dialog_manager: DialogManager, **kwargs):
    current_channel_id = dialog_manager.dialog_data.get("channel_id")
    target_channel_id = dialog_manager.dialog_data.get("target_channel_id")
    transfer_count = dialog_manager.dialog_data.get("transfer_count", 0)
    
    async with get_session() as session:
        current_channel = await session.get(Channel, current_channel_id)
        target_channel = await session.get(Channel, target_channel_id)
        
        # Подсчитываем доступные аккаунты в текущем канале
        available_accounts = await session.scalar(
            select(func.count(Account.number))
            .where(Account.channel_id == current_channel_id)
        ) or 0
    
    return {
        "current_channel_name": current_channel.name if current_channel else "Неизвестно",
        "target_channel_name": target_channel.name if target_channel else "Неизвестно",
        "transfer_count": transfer_count,
        "available_accounts": available_accounts
    }

# Обработчик нажатия кнопки "Перенести аккаунты"
async def on_transfer_accounts(c: CallbackQuery, button: Button, manager: DialogManager):
    channel_id = manager.dialog_data.get('channel_id')
    if not channel_id:
        await c.answer("Ошибка: не выбран канал", show_alert=True)
        return
    
    # Проверяем есть ли аккаунты для переноса
    async with get_session() as session:
        accounts_count = await session.scalar(
            select(func.count(Account.number))
            .where(Account.channel_id == channel_id)
        ) or 0
    
    if accounts_count == 0:
        await c.answer("В этом канале нет аккаунтов для переноса", show_alert=True)
        return
    
    await manager.switch_to(channels.transfer_select_channel)

# Обработчик выбора целевого канала
async def on_target_channel_selected(c: CallbackQuery, widget: Select, manager: DialogManager, item_id: str):
    manager.dialog_data["target_channel_id"] = int(item_id)
    await manager.switch_to(channels.transfer_enter_count)

# Обработчик ввода количества аккаунтов
async def on_transfer_count_entered(
    message: Message,
    widget: TextInput,
    manager: DialogManager,
    data: str
):
    try:
        count = int(data)
        if count <= 0:
            raise ValueError("Количество должно быть больше 0")
    except ValueError:
        await message.answer("Введите корректное положительное число")
        return
    
    # Проверяем доступное количество аккаунтов
    current_channel_id = manager.dialog_data.get("channel_id")
    async with get_session() as session:
        available_count = await session.scalar(
            select(func.count(Account.number))
            .where(Account.channel_id == current_channel_id)
        ) or 0
    
    if count > available_count:
        await message.answer(f"Недостаточно аккаунтов. Доступно: {available_count}")
        return
    
    try:
        await message.delete()
    except Exception:
        pass
    
    manager.dialog_data["transfer_count"] = count
    await manager.switch_to(channels.transfer_confirm, show_mode=ShowMode.EDIT)

# Обработчик подтверждения переноса
async def on_confirm_transfer(c: CallbackQuery, button: Button, manager: DialogManager):
    current_channel_id = manager.dialog_data.get("channel_id")
    target_channel_id = manager.dialog_data.get("target_channel_id")
    transfer_count = manager.dialog_data.get("transfer_count")
    
    if not all([current_channel_id, target_channel_id, transfer_count]):
        await c.answer("Ошибка: не все данные заполнены", show_alert=True)
        return
    
    async with get_session() as session:
        try:
            # Получаем случайные аккаунты для переноса
            accounts_to_transfer = await session.execute(
                select(Account)
                .where(Account.channel_id == current_channel_id)
                .order_by(func.random())
                .limit(transfer_count)
            )
            accounts_to_transfer = accounts_to_transfer.scalars().all()
            
            if len(accounts_to_transfer) != transfer_count:
                await c.answer("Ошибка: недостаточно аккаунтов для переноса", show_alert=True)
                return
            
            # Переносим аккаунты
            transferred = 0
            for account in accounts_to_transfer:
                account.channel_id = target_channel_id
                # Сбрасываем статистику подключения к группе
                account.joined_group = False
                transferred += 1
            
            await session.commit()
            
            # Получаем названия каналов для уведомления
            current_channel = await session.get(Channel, current_channel_id)
            target_channel = await session.get(Channel, target_channel_id)
            
            await c.answer(
                f"✅ Успешно перенесено {transferred} аккаунтов\n"
                f"Из: {current_channel.name}\n"
                f"В: {target_channel.name}",
                show_alert=True
            )
            
            # Возвращаемся в меню канала
            await manager.switch_to(channels.channel_menu, show_mode=ShowMode.EDIT)
            
        except Exception as e:
            await session.rollback()
            logger.error(f"Ошибка переноса аккаунтов: {e}")
            await c.answer("Ошибка при переносе аккаунтов", show_alert=True)

# ОСТАЛЬНЫЕ ФУНКЦИИ (без изменений)

def extract_invite_hash(invite_link: str) -> str:
    patterns = [
        r't\.me/\+([A-Za-z0-9_-]+)',          # https://t.me/+HASH
        r't\.me/joinchat/([A-Za-z0-9_-]+)',   # https://t.me/joinchat/HASH
        r't\.me/([A-Za-z0-9_]+)'              # https://t.me/username
    ]
    
    for pattern in patterns:
        match = re.search(pattern, invite_link)
        if match:
            return match.group(1)
    
    return None

def validate_username(username: str) -> bool:
    """Проверяет корректность username канала"""
    # Убираем @ если есть
    username = username.lstrip('@')
    # Проверяем формат: 5-32 символа, только буквы, цифры и _
    return bool(re.match(r'^[a-zA-Z][a-zA-Z0-9_]{4,31}$', username))

def validate_invite_link(invite_link: str) -> bool:
    """Проверяет корректность инвайт ссылки"""
    return extract_invite_hash(invite_link) is not None

# Обработчики кнопок
async def on_channel_selected(c: CallbackQuery, widget: Select, manager: DialogManager, item_id: str):
    manager.dialog_data['channel_id'] = int(item_id)
    await manager.next()


async def on_add_channel(c: CallbackQuery, button: Button, manager: DialogManager):
    # Очищаем предыдущие данные
    manager.dialog_data.pop('channel_username', None)
    manager.dialog_data.pop('invite_link', None)
    # Переходим в состояние ожидания ввода username канала
    await manager.switch_to(channels.enter_channel_username)


async def on_delete_channel(c: CallbackQuery, button: Button, manager: DialogManager):
    channel_id = manager.dialog_data.get('channel_id')
    if channel_id:
        async with get_session() as session:
            # Получаем канал перед удалением, чтобы знать его имя
            channel = await session.get(Channel, channel_id)
            if not channel:
                await c.answer("Канал не найден", show_alert=True)
                return

            channel_name = channel.name
            # Сбрасываем агентов канала
            await session.execute(
                delete(AIAgent).where(AIAgent.channel_id == channel_id)
            )

            await session.execute(
                delete(Account).where(Account.channel_id == channel_id)
            )

            # Удаляем сам канал
            await session.delete(channel)
            await session.commit()

            # Удаляем папку с фотографиями канала
            try:
                channel_photos_dir = Path(f"media/accounts/{channel_id}")
                if channel_photos_dir.exists():
                    shutil.rmtree(channel_photos_dir)
            except Exception as e:
                print(f"Ошибка при удалении папки с фотографиями: {e}")
                # Не прерываем выполнение, даже если не удалось удалить папку

            await c.answer(f"Канал {channel_name} удален", show_alert=True)
            await manager.switch_to(channels.main_menu, show_mode=ShowMode.EDIT)
            return

    await c.answer("Не удалось удалить канал", show_alert=True)


async def on_select_agent(c: CallbackQuery, widget: Select, manager: DialogManager, item_id: str):
    channel_id = manager.dialog_data.get('channel_id') or manager.start_data.get('channel_id')
    if not channel_id:
        await c.answer("Ошибка: не выбран канал", show_alert=True)
        return

    await manager.start(
        state=agents.agent_info,
        show_mode=ShowMode.EDIT,
        data={
            'channel_id': channel_id,
            'selected_agent_id': int(item_id)
        }
    )


async def on_add_accounts(c: CallbackQuery, button: Button, manager: DialogManager):
    channel_id = manager.dialog_data.get('channel_id')
    if not channel_id:
        channel_id=manager.start_data.get('channel_id')
    await manager.start(state=accounts.wait_zip_file, show_mode=ShowMode.EDIT, data={'channel_id':channel_id})

async def on_confirm_channel(c: CallbackQuery, button: Button, manager: DialogManager):
    channel_username = manager.dialog_data.get('channel_username')
    invite_link = manager.dialog_data.get('invite_link')
    
    if not channel_username or not invite_link:
        await c.answer("Ошибка: не указаны все данные", show_alert=True)
        return

    async with get_session() as session:
        # Проверяем, существует ли уже такой канал
        existing_channel = await session.execute(
            select(Channel).where(Channel.name == channel_username))
        existing_channel = existing_channel.scalar_one_or_none()

        if existing_channel:
            await c.answer(
                f"Канал {channel_username} уже существует!",
                show_alert=True
            )
            return

        # Если канала нет - добавляем
        new_channel = Channel(
            name=channel_username,
            discussion_group_invite=invite_link
        )
        session.add(new_channel)
        await session.commit()
        await c.answer(f"Канал {channel_username} успешно добавлен", show_alert=True)
        await manager.switch_to(state=channels.main_menu)

# Универсальный обработчик для редактирования параметров канала
async def on_edit_param(c: CallbackQuery, button: Button, manager: DialogManager):
    param_name = button.widget_id
    manager.dialog_data["editing_param"] = param_name
    await manager.switch_to(channels.edit_param)

# Универсальный обработчик ввода параметров
async def on_param_input(
        message: Message,
        widget: TextInput,
        manager: DialogManager,
        data: str
):
    param_name = manager.dialog_data.get("editing_param")
    if not param_name:
        return

    try:
        # Для reaction_types принимаем строку, для остальных - число
        if param_name == "likes_reaction_types":
            # Проверяем формат реакций (эмодзи через запятую)
            reactions = [r.strip() for r in data.split(',') if r.strip()]
            if not reactions:
                raise ValueError("Введите хотя бы одну реакцию")
            value = ','.join(reactions)
        else:
            value = int(data)
            if value < 0:
                raise ValueError("Значение должно быть положительным")
    except ValueError as e:
        await message.answer(f"Некорректное значение: {str(e)}")
        return

    try:
        await message.delete()
    except Exception:
        pass

    channel_id = manager.dialog_data.get("channel_id")
    if not channel_id:
        channel_id = manager.start_data.get("channel_id")
    
    async with get_session() as session:
        channel = await session.get(Channel, channel_id)
        if channel:
            setattr(channel, param_name, value)
            await session.commit()

    await manager.switch_to(channels.channel_menu, show_mode=ShowMode.EDIT)

# Обработчики для загрузки списков
async def on_upload_male_names(c: CallbackQuery, button: Button, manager: DialogManager):
    manager.dialog_data["uploading_type"] = "male_names"
    await manager.switch_to(channels.upload_list)

async def on_upload_female_names(c: CallbackQuery, button: Button, manager: DialogManager):
    manager.dialog_data["uploading_type"] = "female_names"
    await manager.switch_to(channels.upload_list)

async def on_upload_male_photos(c: CallbackQuery, button: Button, manager: DialogManager):
    manager.dialog_data["uploading_type"] = "male_photos"
    await manager.switch_to(channels.upload_photos)

async def on_upload_female_photos(c: CallbackQuery, button: Button, manager: DialogManager):
    manager.dialog_data["uploading_type"] = "female_photos"
    await manager.switch_to(channels.upload_photos)

async def on_list_uploaded(
        message: Message,
        widget: TextInput,
        manager: DialogManager,
        data: str
):
    upload_type = manager.dialog_data.get("uploading_type")
    if not upload_type:
        return

    channel_id = manager.dialog_data.get('channel_id')
    if not channel_id:
        await message.answer("Ошибка: не выбран канал")
        return

    channel_id = manager.dialog_data.get('channel_id')
    async with get_session() as session:
        channel = await session.get(Channel, channel_id)
        if channel:
            if upload_type == "male_names":
                channel.acc_male_name_list = data
            elif upload_type == "female_names":
                channel.acc_female_name_list = data
            await session.commit()

    await message.delete()
    await manager.switch_to(channels.channel_menu, show_mode=ShowMode.EDIT)

# Обработчик для принятия ZIP-файла
async def on_photos_uploaded(
        message: Message,
        widget: MessageInput,
        manager: DialogManager,
):
    if not message.document or not message.document.file_name.endswith('.zip'):
        await message.answer("Пожалуйста, отправьте ZIP-архив с фотографиями")
        return

    channel_id = manager.dialog_data.get('channel_id')
    upload_type = manager.dialog_data.get("uploading_type")
    
    if not channel_id or not upload_type:
        await message.answer("Ошибка: не выбран канал или тип загрузки")
        return

    # Создаем папку для канала и пола
    gender_folder = "male" if upload_type == "male_photos" else "female"
    channel_folder = Path(f"media/accounts/{channel_id}/{gender_folder}")
    channel_folder.mkdir(parents=True, exist_ok=True)

    try:
        # Скачиваем файл
        zip_file = Path(f"downloads/{message.document.file_name}")
        await message.bot.download(
            message.document.file_id,
            destination=zip_file
        )

        # Распаковываем архив
        with zipfile.ZipFile(zip_file, 'r') as zip_ref:
            zip_ref.extractall(channel_folder)

        # Удаляем временный файл
        os.remove(zip_file)

        # Сохраняем путь к папке в базу данных
        async with get_session() as session:
            channel = await session.get(Channel, channel_id)
            if channel:
                if upload_type == "male_photos":
                    channel.acc_male_photo_list = str(channel_folder)
                elif upload_type == "female_photos":
                    channel.acc_female_photo_list = str(channel_folder)
                await session.commit()
        await message.delete()
    except Exception as e:
        await message.answer(f"Ошибка при обработке архива: {str(e)}")
    finally:
        await manager.switch_to(channels.channel_menu, show_mode=ShowMode.EDIT)


# Виджеты для главного меню
channels_group = Group(
    Select(
        Format("{item.name}"),
        id="channels_menu",
        item_id_getter=lambda x: str(x.id),
        items="channels_menu",
        on_click=on_channel_selected,
    )
)

async def on_click_add_agent_menu(c: CallbackQuery, button: Button, manager: DialogManager):
    channel_id = manager.dialog_data.get('channel_id')
    await manager.start(
        state=agents.enter_api_id,
        data={
            "channel_id": channel_id
        },
        show_mode=ShowMode.EDIT
    )

# Виджеты для меню канала (ОБНОВЛЕНЫ С КНОПКОЙ ПЕРЕНОСА)
channel_actions_group = Group(
    Select(
        Format("{item[agent].description} {item[status]}"),
        id="agents",
        item_id_getter=lambda x: str(x["agent"].agent_id),
        items="agents",
        on_click=on_select_agent,
    ),
    
    # Параметры комментариев
    Button(
        Format("Шанс комментов: {comments_chance}%"),
        id="comments_chance",
        on_click=on_edit_param,
    ),
    Button(
        Format("Количество комментов: {comments_number}"),
        id="comments_number",
        on_click=on_edit_param,
    ),
    Button(
        Format("Диапазон комментов: {comments_number_range}"),
        id="comments_number_range",
        on_click=on_edit_param,
    ),
    
    # Параметры выбора постов
    Button(
        Format("Шанс выбора поста: {post_selection_chance}%"),
        id="post_selection_chance",
        on_click=on_edit_param,
    ),
    Button(
        Format("Мин интервал постов: {post_min_interval} мин"),
        id="post_min_interval",
        on_click=on_edit_param,
    ),
    Button(
        Format("Макс интервал постов: {post_max_interval} мин"),
        id="post_max_interval",
        on_click=on_edit_param,
    ),
    
    # Параметры лайков
    Button(
        Format("Шанс лайков постов: {likes_on_posts_chance}%"),
        id="likes_on_posts_chance",
        on_click=on_edit_param,
    ),
    Button(
        Format("Шанс лайков комментов: {likes_on_comments_chance}%"),
        id="likes_on_comments_chance",
        on_click=on_edit_param,
    ),
    Button(
        Format("Типы реакций: {likes_reaction_types}"),
        id="likes_reaction_types",
        on_click=on_edit_param,
    ),
    
    # Кнопки для загрузки списков (разделенные по полу)
    Button(
        Const("ЗАГРУЗИТЬ МУЖСКИЕ ИМЕНА"),
        id="upload_male_names",
        on_click=on_upload_male_names,
    ),
    Button(
        Const("ЗАГРУЗИТЬ ЖЕНСКИЕ ИМЕНА"),
        id="upload_female_names",
        on_click=on_upload_female_names,
    ),
    Button(
        Const("ЗАГРУЗИТЬ МУЖСКИЕ АВАТАРКИ"),
        id="upload_male_photos",
        on_click=on_upload_male_photos,
    ),
    Button(
        Const("ЗАГРУЗИТЬ ЖЕНСКИЕ АВАТАРКИ"),
        id="upload_female_photos",
        on_click=on_upload_female_photos,
    ),
    Button(
        Const("ДОБАВИТЬ АККАУНТЫ"),
        id="add_accounts",
        on_click=on_add_accounts,
    ),
    Button(
        Const("ДОБАВИТЬ АГЕНТА"),
        id="add_agent",
        on_click=on_click_add_agent_menu,
    ),
    # НОВАЯ КНОПКА ПЕРЕНОСА АККАУНТОВ
    Button(
        Const("↔️ ПЕРЕНЕСТИ АККАУНТЫ"),
        id="transfer_accounts",
        on_click=on_transfer_accounts,
    ),
    Button(
        Const("УДАЛИТЬ КАНАЛ"),
        id="delete_channel",
        on_click=on_delete_channel,
    ),
    Back(Const("НАЗАД")),
)

async def on_channel_username_entered(message: Message, widget: TextInput, manager: DialogManager, text: str):
    # Валидация username
    if not validate_username(text):
        await message.answer("❌ Некорректный username канала!\n\nПример: @mychannel или mychannel")
        return
    
    await message.delete()
    # Убираем @ если есть и добавляем обратно для единообразия
    clean_username = text.lstrip('@')
    manager.dialog_data['channel_username'] = f"@{clean_username}"
    await manager.switch_to(channels.enter_invite_link, show_mode=ShowMode.EDIT)

async def on_invite_link_entered(message: Message, widget: TextInput, manager: DialogManager, text: str):
    # Валидация инвайт ссылки
    if not validate_invite_link(text):
        await message.answer("❌ Некорректная инвайт ссылка!")
        return
    
    await message.delete()
    manager.dialog_data['invite_link'] = text
    await manager.switch_to(channels.confirm_channel, show_mode=ShowMode.EDIT)

# Виджеты для ожидания ввода username канала
enter_channel_username_window = Window(
    Const("Введите username канала:\n\n<b>Пример:</b> @mychannel или mychannel"),
    TextInput(id="channel_username_input",
        on_success=on_channel_username_entered),
    SwitchTo(Const("НАЗАД"), state=channels.main_menu, id='channel_back_button'),
    state=channels.enter_channel_username,
)

# Виджеты для ожидания ввода инвайт ссылки
enter_invite_link_window = Window(
    Const("Введите инвайт ссылку на группу обсуждений:"),
    TextInput(id="invite_link_input",
        on_success=on_invite_link_entered),
    Back(Const("НАЗАД")),
    state=channels.enter_invite_link,
)

# Виджеты для подтверждения добавления канала
confirm_channel_group = Group(
    Button(
        Const("✅ ПОДТВЕРДИТЬ"),
        id="confirm_add_channel",
        on_click=on_confirm_channel,
    ),
    Url(
        Const("🔗 КАНАЛ"),
        id="channel_url",
        url=Format("{channel_url}"),
        when="channel_url"
    ),
    Back(Const("НАЗАД")),
)

# Диалоги
channels_dialog = Dialog(
    Window(
        Const("<b>УПРАВЛЕНИЕ КАНАЛАМИ</b>"),
        Group(channels_group, width=2),
        Button(
            Const("ДОБАВИТЬ КАНАЛ"),
            id="add_channel",
            on_click=on_add_channel,
        ),
        Button(Const("НАЗАД"), on_click=on_click_back_main_menu, id='channel_back_button'),
        state=channels.main_menu,
        getter=channels_menu_getter,
    ),
    Window(
        Format(
            "<b>Канал:</b> <i>{channel_name}</i>\n"
            "<b>Инвайт группы:</b> <code>{discussion_group_invite}</code>\n"
            "<b>ID группы:</b> <code>{discussion_group_id}</code>\n"
            "<b>Текущий агент:</b> {active_agent}\n\n"
            "<b>📝 Комментарии:</b>\n"
            "• Шанс: {comments_chance}%\n"
            "• Количество: {comments_number} ± {comments_number_range}\n\n"
            "<b>📊 Выбор постов:</b>\n"
            "• Шанс выбора: {post_selection_chance}%\n"
            "• Интервал: {post_min_interval}-{post_max_interval} мин\n\n"
            "<b>👍 Лайки:</b>\n"
            "• На посты: {likes_on_posts_chance}%\n"
            "• На комментарии: {likes_on_comments_chance}%\n"
            "• Реакции: {likes_reaction_types}"
        ),
        channel_actions_group,
        state=channels.channel_menu,
        getter=channel_actions_getter,
    ),
    enter_channel_username_window,
    enter_invite_link_window,
    Window(
        Format(
            "Проверьте данные перед добавлением:\n\n"
            "<b>Username канала:</b> {channel_username}\n"
            "<b>Инвайт ссылка группы:</b> <code>{invite_link}</code>"
        ),
        confirm_channel_group,
        state=channels.confirm_channel,
        getter=confirm_channel_getter,
    ),
    # Окно редактирования параметров
    Window(
        Format(
            "Введите новое значение для параметра:\n\n"
            "• Для числовых параметров: введите число\n"
            "• Для реакций: введите эмодзи через запятую (например: ❤️,👍,🔥)"
        ),
        TextInput(
            id="param_input",
            on_success=on_param_input
        ),
        SwitchTo(Const("НАЗАД"), state=channels.channel_menu, id='param_back_button'),
        state=channels.edit_param
    ),
    Window(
        Const("Отправьте список (каждое значение с новой строки):"),
        TextInput(
            id="list_upload_input",
            on_success=on_list_uploaded
        ),
        SwitchTo(Const("НАЗАД"), state=channels.channel_menu, id='list_back_button'),
        state=channels.upload_list
    ),
    Window(
        Const("Отправьте ZIP-архив с фотографиями для аватарок:"),
        MessageInput(
            func=on_photos_uploaded,
            content_types=["document"]
        ),
        SwitchTo(Const("НАЗАД"), state=channels.channel_menu, id='photos_back_button'),
        state=channels.upload_photos
    ),
    # НОВЫЕ ОКНА ДЛЯ ПЕРЕНОСА АККАУНТОВ
    # Окно выбора целевого канала для переноса
    Window(
        Const("Выберите канал, в который хотите перенести аккаунты:"),
        Select(
            Format("{item.name}"),
            id="target_channels",
            item_id_getter=lambda x: str(x.id),
            items="channels",
            on_click=on_target_channel_selected,
        ),
        SwitchTo(Const("НАЗАД"), state=channels.channel_menu, id='transfer_back1'),
        state=channels.transfer_select_channel,
        getter=get_transfer_channels
    ),
    # Окно ввода количества аккаунтов
    Window(
        Const("Введите количество аккаунтов для переноса:"),
        TextInput(
            id="transfer_count_input",
            on_success=on_transfer_count_entered
        ),
        Back(Const("НАЗАД")),
        state=channels.transfer_enter_count
    ),
    # Окно подтверждения переноса
    Window(
        Format(
            "Подтвердите перенос аккаунтов:\n\n"
            "📤 Из канала: <b>{current_channel_name}</b>\n"
            "📥 В канал: <b>{target_channel_name}</b>\n"
        ),
        Button(
            Const("✅ ПОДТВЕРДИТЬ ПЕРЕНОС"),
            id="confirm_transfer",
            on_click=on_confirm_transfer,
        ),
        Back(Const("❌ ОТМЕНА")),
        state=channels.transfer_confirm,
        getter=get_transfer_confirmation
    )
)