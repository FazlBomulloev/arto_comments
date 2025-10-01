from aiogram_dialog import Dialog, Window, DialogManager, ShowMode
from aiogram_dialog.widgets.kbd import Button, Select, Back, Group
from aiogram_dialog.widgets.text import Const, Format
from aiogram.types import CallbackQuery, Message
from aiogram_dialog.widgets.input import TextInput
from sqlalchemy import select

from src.db import get_session
from src.db.models import AIAgent
from ...states import agents, channels

from .utils import on_back_channel_menu


# Геттер для списка агентов
async def agent_info_getter(dialog_manager: DialogManager, **kwargs):
    agent_id = dialog_manager.start_data.get('selected_agent_id')
    channel_id = dialog_manager.start_data.get('channel_id')

    if not agent_id:
        return {
            "agent_id": "Не указан",
            "api_id": "Не указан",
            "description": "Агент не найден",
            "status": "❌",
            "is_active": False
        }

    async with get_session() as session:
        agent = await session.get(AIAgent, agent_id)
        if not agent:
            return {
                "agent_id": agent_id,
                "api_id": "Не найден",
                "description": "Агент не найден в базе",
                "status": "❌",
                "is_active": False
            }

        # Проверяем, активен ли этот агент для канала
        active_agent = await session.execute(
            select(AIAgent).where(
                AIAgent.channel_id == channel_id,
                AIAgent.status == True
            )
        )
        active_agent = active_agent.scalar_one_or_none()
        is_active = active_agent and active_agent.agent_id == agent_id

    return {
        "agent_id": agent.agent_id,
        "api_id": agent.api_id,
        "description": agent.description,
        "status": "✅" if is_active else "❌",
        "is_active": is_active
    }

async def on_disable_agent(c: CallbackQuery, button: Button, manager: DialogManager):
    agent_id = manager.start_data.get('selected_agent_id')
    channel_id = manager.start_data.get('channel_id')

    if not agent_id or not channel_id:
        await c.answer("Ошибка: не выбран агент или канал", show_alert=True)
        return

    async with get_session() as session:
        # Находим текущего активного агента
        active_agent = await session.execute(
            select(AIAgent).where(
                AIAgent.channel_id == channel_id,
                AIAgent.status == True
            )
        )
        active_agent = active_agent.scalar_one_or_none()

        # Если это действительно активный агент - деактивируем
        if active_agent and active_agent.agent_id == agent_id:
            active_agent.status = False
            session.add(active_agent)
            await session.commit()
            await c.answer(f"Агент {active_agent.description} выключен", show_alert=True)
        else:
            await c.answer("Этот агент уже не активен", show_alert=True)

    # Обновляем информацию об агенте
    await manager.switch_to(agents.agent_info)

# Геттер для подтверждения создания агента
async def confirm_new_agent_getter(dialog_manager: DialogManager, **kwargs):
    api_id = dialog_manager.dialog_data.get('api_id', 'Не указан')
    description = dialog_manager.dialog_data.get('description', 'Не указано')

    return {
        "api_id": api_id,
        "description": description,
    }


# Обработчики ввода данных
async def on_api_id_entered(message: Message, widget: TextInput, manager: DialogManager, text: str):
    await message.delete()
    manager.dialog_data['api_id'] = text
    manager.dialog_data['channel_id'] = manager.start_data['channel_id']
    await manager.switch_to(agents.enter_description, show_mode=ShowMode.EDIT)


async def on_description_entered(message: Message, widget: TextInput, manager: DialogManager, text: str):
    await message.delete()
    manager.dialog_data['description'] = text
    manager.dialog_data['channel_id'] = manager.start_data['channel_id']
    await manager.switch_to(agents.confirm_agent, show_mode=ShowMode.EDIT)


# Обработчики кнопок
async def on_confirm_new_agent(c: CallbackQuery, button: Button, manager: DialogManager):
    channel_id = manager.start_data['channel_id']
    api_id = manager.dialog_data.get('api_id')
    description = manager.dialog_data.get('description')

    if not api_id or not description:
        await c.answer("❌ Ошибка: не указаны все данные", show_alert=True)
        return

    try:
        async with get_session() as session:
            # Проверяем, есть ли уже агент с таким api_id в этом канале
            existing_agent = await session.execute(
                select(AIAgent)
                .where(AIAgent.api_id == api_id)
                .where(AIAgent.channel_id == channel_id)
            )
            if existing_agent.scalar():
                await c.answer(
                    "❌ Агент с таким API ID уже существует в этом канале!",
                    show_alert=True
                )
                return

            # Создаём нового агента
            new_agent = AIAgent(
                api_id=api_id,
                description=description,
                channel_id=channel_id,
                status=False
            )
            session.add(new_agent)
            await session.commit()

            await c.answer(
                f"✅ Агент успешно создан!\n"
                f"API ID: {api_id}\n"
                f"Описание: {description}",
                show_alert=True
            )
            await manager.done()

    except Exception as e:
        await c.answer(f"⚠️ Ошибка при создании агента: {e}", show_alert=True)

# Окно ввода API ID
enter_api_id_window = Window(
    Const("Введите API ID агента:"),
    TextInput(
        id="api_id_input",
        on_success=on_api_id_entered
    ),
    Button(Const("Назад"), on_click=on_back_channel_menu, id='back_button'),
    state=agents.enter_api_id,
)

# Окно ввода описания
enter_description_window = Window(
    Const("Введите описание агента:"),
    TextInput(
        id="description_input",
        on_success=on_description_entered,
    ),
    Back(Const("Назад")),
    state=agents.enter_description,
)

# Окно подтверждения создания агента
confirm_new_agent_window = Window(
    Format(
        "Подтвердите создание агента:\n\n"
        "API ID: <b>{api_id}</b>\n"
        "Описание: <b>{description}</b>"
    ),
    Button(
        Const("ПОДТВЕРДИТЬ СОЗДАНИЕ"),
        id="confirm_new_agent",
        on_click=on_confirm_new_agent,
    ),
    Back(Const("Назад")),
    state=agents.confirm_agent,
    getter=confirm_new_agent_getter,
)


# Обработчики кнопок
async def on_agent_selected(c: CallbackQuery, widget: Select, manager: DialogManager, item_id: str):
    agent_id = int(item_id)
    async with get_session() as session:
        agent = await session.get(AIAgent, agent_id)
        if not agent:
            await c.answer("Агент не найден", show_alert=True)
            return

    manager.dialog_data['selected_agent_id'] = agent_id
    await manager.switch_to(agents.agent_info, show_mode=ShowMode.EDIT)


async def on_select_agent(c: CallbackQuery, button: Button, manager: DialogManager):
    agent_id = manager.start_data.get('selected_agent_id')
    channel_id = manager.start_data.get('channel_id')

    if not agent_id or not channel_id:
        await c.answer("Ошибка: не выбран агент или канал", show_alert=True)
        return

    async with get_session() as session:
        # Сбрасываем статус у текущего активного агента
        current_active = await session.execute(
            select(AIAgent).where(
                AIAgent.channel_id == channel_id,
                AIAgent.status == True
            )
        )
        current_active = current_active.scalar_one_or_none()

        if current_active:
            current_active.status = False
            session.add(current_active)

        # Устанавливаем статус новому агенту
        new_agent = await session.get(AIAgent, agent_id)
        if not new_agent:
            await c.answer("Агент не найден", show_alert=True)
            return

        new_agent.status = True
        new_agent.channel_id = channel_id
        session.add(new_agent)
        await session.commit()

    await c.answer(f"Агент {new_agent.description} выбран для канала", show_alert=True)
    await manager.switch_to(agents.agent_info)  # Возвращаем в меню агента с обновленными данными


async def on_delete_agent(c: CallbackQuery, button: Button, manager: DialogManager):
    agent_id = manager.dialog_data.get('selected_agent_id')
    if not agent_id:
        agent_id = manager.start_data.get('selected_agent_id')
    if not agent_id:
        await c.answer("Не выбран агент для удаления", show_alert=True)
        return

    channel_id = manager.dialog_data.get('channel_id')
    if not channel_id:
        channel_id = manager.start_data.get('channel_id')

    async with get_session() as session:
        agent = await session.get(AIAgent, agent_id)
        if not agent:
            await c.answer("Агент не найден", show_alert=True)
            await manager.start(state=channels.channel_menu,show_mode=ShowMode.EDIT)
            return

        await session.delete(agent)
        await session.commit()
        await c.answer(f"Агент {agent_id} удален", show_alert=True)
        await manager.start(state=channels.channel_menu, show_mode=ShowMode.EDIT, data={'channel_id':channel_id})

# Окно информации об агенте
agent_info_window = Window(
    Format(
        "<b>Информация об агенте:</b>\n\n"
        "AGENT ID: <code>{agent_id}</code>\n"
        "API ID: <code>{api_id}</code>\n"
        "Описание: {description}\n"
        "Статус: {status}"
    ),
    Group(
        Button(
            Const("✅ ВЫБРАТЬ"),
            id="select_agent",
            on_click=on_select_agent,
            when=lambda data, widget, manager: not data["is_active"]  # Показываем только если не активен
        ),
        Button(
            Const("🔴 ВЫКЛЮЧИТЬ"),
            id="disable_agent",
            on_click=on_disable_agent,
            when=lambda data, widget, manager: data["is_active"]  # Показываем только если активен
        ),
        Button(
            Const("❌ УДАЛИТЬ"),
            id="delete_agent",
            on_click=on_delete_agent,
        ),
    ),
    Button(Const("Назад"), on_click=on_back_channel_menu, id='back_button'),
    state=agents.agent_info,
    getter=agent_info_getter,
)

# Обновленный диалог
add_agent_dialog = Dialog(
    agent_info_window,
    enter_api_id_window,
    enter_description_window,
    confirm_new_agent_window,
)