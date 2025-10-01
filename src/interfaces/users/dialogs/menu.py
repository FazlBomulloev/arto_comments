from aiogram_dialog import Dialog, Window, ShowMode
from aiogram.types import CallbackQuery, ContentType
from aiogram_dialog.widgets.text import Const, Format
from aiogram_dialog.widgets.kbd import Button, Row, Url
from src.interfaces.users.states import menu, channels, settings, stats
from aiogram_dialog import DialogManager
from aiogram_dialog.widgets.media import StaticMedia
from pathlib import Path
from aiogram_dialog.widgets.kbd import SwitchTo
from .utils import on_click_empty_func
from sqlalchemy import select, func
from src.db import get_session
from src.db.models import Account

async def on_click_channels(call: CallbackQuery, button: Button, manager: DialogManager):
    await manager.start(show_mode=ShowMode.EDIT, state=channels.main_menu)

async def on_click_stats(call: CallbackQuery, button: Button, manager: DialogManager):
    await manager.start(show_mode=ShowMode.EDIT, state=stats.channel_select)

async def on_click_settings(call: CallbackQuery, button: Button, manager: DialogManager):
    await manager.start(show_mode=ShowMode.EDIT, state=settings.main_menu)

async def on_click_recovery(call: CallbackQuery, button: Button, manager: DialogManager):
    """Запуск ручного восстановления аккаунтов"""
    from src.accounts.recovery import AccountRecoveryManager
    
    try:
        await call.answer("🔄 Запуск восстановления аккаунтов...", show_alert=False)
        
        # Запускаем восстановление
        await AccountRecoveryManager.run_recovery_cycle()
        
        await call.answer("✅ Восстановление завершено! Проверьте статистику.", show_alert=True)
        
    except Exception as e:
        await call.answer(f"❌ Ошибка восстановления: {str(e)}", show_alert=True)

async def get_main_menu_data(dialog_manager: DialogManager, **kwargs):
    """Получаем статистику для главного меню"""
    async with get_session() as session:
        # Считаем количество аккаунтов по статусам
        active_count = await session.scalar(
            select(func.count(Account.number)).where(Account.status == 'active')
        ) or 0
        
        pause_count = await session.scalar(
            select(func.count(Account.number)).where(Account.status == 'pause')
        ) or 0
        
        ban_count = await session.scalar(
            select(func.count(Account.number)).where(Account.status == 'ban')
        ) or 0
    
    return {
        "active_count": active_count,
        "pause_count": pause_count,
        "ban_count": ban_count,
        "total_count": active_count + pause_count + ban_count
    }

main_menu_window = Window(
    Format(
        '<b>ГЛАВНОЕ МЕНЮ</b>\n\n'
        '👥 <b>Статус аккаунтов:</b>\n'
        '✅ Активных: {active_count}\n'
        '⏸ На паузе: {pause_count}\n'
        '🚫 Заблокировано: {ban_count}\n'
        '📊 Всего: {total_count}'
    ),
    Button(
        Const("📺 КАНАЛЫ"),
        id="channels_dialogs",
        on_click=on_click_channels
    ),
    Button(
        Const("⚙️ НАСТРОЙКИ"),
        id="settings",
        on_click=on_click_settings
    ),
    Button(
        Const("📊 СТАТИСТИКА"),
        id="statistic",
        on_click=on_click_stats
    ),
    state=menu.main_menu,
    getter=get_main_menu_data
)

menu_dialog = Dialog(main_menu_window)