from aiogram_dialog import Dialog, Window, DialogManager, ShowMode
from aiogram_dialog.widgets.kbd import Back, Button, Row, Column
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.input import TextInput
from aiogram.types import Message, CallbackQuery

from src.params.db_manager import DatabaseManager
from ..states import settings
from .utils import on_click_back_main_menu

DELAY_PARAMS = {
    "comment_delay": "Базовая задержка (мин)",
    "comment_range": "Диапазон рандома (мин)"
}


async def get_delay_params(dialog_manager: DialogManager, **kwargs):
    db = DatabaseManager()
    params = {}
    for key in DELAY_PARAMS:
        value = await db.get_parameter(key)
        params[key] = value or "Не установлено"
    return params


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
        value = float(data)
        if value < 0:
            raise ValueError
    except ValueError:
        await message.answer("Введите корректное число (больше или равно 0)")
        return

    # Удаляем сообщение с вводом пользователя
    try:
        await message.delete()
    except Exception as e:
        pass  # Игнорируем ошибки удаления

    db = DatabaseManager()
    await db.set_parameter(param_name, str(value))

    # Получаем обновленные параметры
    updated_params = await get_delay_params(manager)

    # Редактируем сообщение с меню
    await manager.start(settings.main_menu, data=updated_params, show_mode=ShowMode.EDIT)


async def select_param(
        callback: CallbackQuery,
        button: Button,
        manager: DialogManager
):
    param_name = button.widget_id
    manager.dialog_data["editing_param"] = param_name
    await manager.switch_to(settings.param_input)


settings_dialog = Dialog(
    Window(
        Const("⚙️ Настройки задержки между комментариями"),
        Column(
            *[
                Button(
                    Format(f"{desc}: {{{key}}}"),
                    id=key,
                    on_click=select_param
                )
                for key, desc in DELAY_PARAMS.items()
            ]
        ),
        Row(Button(Const("НАЗАД"), on_click=on_click_back_main_menu, id='settings_back_button')),
        state=settings.main_menu,
        getter=get_delay_params
    ),
    Window(
        Const("Введите новое значение (в минутах):"),
        TextInput(
            id="param_input",
            on_success=on_param_input
        ),
        state=settings.param_input
    )
)