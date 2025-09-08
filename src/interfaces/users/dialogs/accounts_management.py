from aiogram_dialog import Dialog, Window, DialogManager, ShowMode
from aiogram_dialog.widgets.kbd import Button, Back, Column, Row
from aiogram_dialog.widgets.text import Const, Format
from aiogram.types import CallbackQuery
from sqlalchemy import select

from src.db import get_session
from src.db.models import Channel
from src.accounts.status_manager import AccountStatusManager
from src.accounts.recovery_scheduler import recovery_scheduler
from ..states import account_management
from .utils import on_click_back_main_menu

async def get_account_stats(dialog_manager: DialogManager, **kwargs):
    # Получаем общую статистику
    stats = await AccountStatusManager.get_accounts_statistics()
    
    # Статус планировщика
    scheduler_status = await recovery_scheduler.get_scheduler_status()
    
    return {
        "stats": stats,
        "scheduler": scheduler_status
    }

async def on_force_recovery(c: CallbackQuery, button: Button, manager: DialogManager):
    try:
        await recovery_scheduler.trigger_recovery_now()
        await c.answer("✅ Принудительное восстановление запущено", show_alert=True)
    except Exception as e:
        await c.answer(f"❌ Ошибка: {e}", show_alert=True)

async def get_channel_stats(dialog_manager: DialogManager, **kwargs):
    async with get_session() as session:
        result = await session.execute(select(Channel))
        channels = result.scalars().all()
        
        channel_stats = []
        for channel in channels:
            stats = await AccountStatusManager.get_accounts_statistics(channel.id)
            channel_stats.append({
                "channel": channel,
                "stats": stats
            })
    
    return {"channel_stats": channel_stats}

accounts_management_dialog = Dialog(
    Window(
        Format(
            "👥 <b>Управление аккаунтами</b>\n\n"
            "📊 <b>Общая статистика:</b>\n"
            "• Всего аккаунтов: {stats[total]}\n"
            "• ✅ Активных: {stats[active]} ({stats[percentages][active]}%)\n"
            "• ⏸ В паузе: {stats[pause]} ({stats[percentages][pause]}%)\n"
            "• 🚫 Забанено: {stats[ban]} ({stats[percentages][ban]}%)\n"
            "• 🔄 Готово к восстановлению: {stats[ready_for_recovery][total]}\n\n"
            "🤖 <b>Планировщик:</b> {'🟢 Работает' if scheduler[running] else '🔴 Остановлен'}"
        ),
        Column(
            Button(
                Const("🔄 Принудительное восстановление"),
                id="force_recovery",
                on_click=on_force_recovery
            ),
            Button(
                Const("📈 Статистика по каналам"),
                id="channel_stats",
                on_click=lambda c, b, m: m.switch_to(account_management.channel_stats)
            ),
        ),
        Back(Const("НАЗАД"), on_click=on_click_back_main_menu),
        state=account_management.main_menu,
        getter=get_account_stats
    ),
    Window(
        Const("📈 <b>Статистика по каналам</b>\n"),
        Format(
            "{% for item in channel_stats %}"
            "<b>{item[channel].name}:</b>\n"
            "• Активных: {item[stats][active]}\n"
            "• В паузе: {item[stats][pause]}\n"
            "• Забанено: {item[stats][ban]}\n\n"
            "{% endfor %}"
        ),
        Back(Const("НАЗАД")),
        state=account_management.channel_stats,
        getter=get_channel_stats
    )
)