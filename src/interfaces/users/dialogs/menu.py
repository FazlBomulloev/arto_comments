from aiogram_dialog import Dialog, Window, ShowMode
from aiogram.types import CallbackQuery, ContentType
from aiogram_dialog.widgets.text import Const
from aiogram_dialog.widgets.kbd import Button, Row, Url
from src.interfaces.users.states import menu, channels, settings, stats, account_management  # НОВОЕ: добавлен account_management
from aiogram_dialog import DialogManager
from aiogram_dialog.widgets.media import StaticMedia
from pathlib import Path
from aiogram_dialog.widgets.kbd import SwitchTo
from .utils import  on_click_empty_func

async def on_click_channels(call: CallbackQuery, button: Button,  manager: DialogManager):
    await manager.start(show_mode=ShowMode.EDIT, state=channels.main_menu)

async def on_click_stats(call: CallbackQuery, button: Button,  manager: DialogManager):
    await manager.start(show_mode=ShowMode.EDIT, state=stats.channel_select)

async def on_click_settings(call: CallbackQuery, button: Button,  manager: DialogManager):
    await manager.start(show_mode=ShowMode.EDIT, state=settings.main_menu)

# НОВОЕ: Обработчик для управления аккаунтами
async def on_click_accounts(call: CallbackQuery, button: Button, manager: DialogManager):
    await manager.start(show_mode=ShowMode.EDIT, state=account_management.main_menu)

main_menu_window = Window(
    Const('<b>ГЛАВНОЕ МЕНЮ</b>'),
    Button(
        Const("КАНАЛЫ"),  # Эмодзи робота для ИИ помощника
        id="channels_dialogs",
        on_click=on_click_channels
    ),
    Button(
        Const("НАСТРОЙКИ"),  # Эмодзи робота для ИИ помощника
        id="settings",
        on_click=on_click_settings
    ),
    Button(
        Const("СТАТИСТИКА"),  # Эмодзи робота для ИИ помощника
        id="statistic",
        on_click=on_click_stats
    ),
    state=menu.main_menu
)
menu_dialog = Dialog(main_menu_window)