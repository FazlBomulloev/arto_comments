from aiogram_dialog import Dialog, Window, DialogManager, ShowMode
from aiogram_dialog.widgets.kbd import Back, Button, Select, Column
from aiogram_dialog.widgets.text import Const, Format
from aiogram.types import CallbackQuery
from sqlalchemy import select, func, and_
from sqlalchemy.future import select as async_select
from datetime import datetime, timedelta

from src.db import get_session
from src.db.models import Account, Channel, CommentActivity, PostActivity
from ..states import stats
from .utils import on_click_back_main_menu


async def get_channels(dialog_manager: DialogManager, **kwargs):
    async with get_session() as session:
        result = await session.execute(select(Channel))
        channels = result.scalars().all()
    return {
        "channels": channels,
    }


async def get_stats(dialog_manager: DialogManager, **kwargs):
    channel_id = dialog_manager.dialog_data.get("channel_id")
    if not channel_id:
        return {"stats": None}

    async with get_session() as session:
        # Получаем название канала
        channel = await session.get(Channel, channel_id)

        # Статистика по статусам аккаунтов
        account_stats = {
            "active": await session.scalar(
                async_select(func.count(Account.number))
                .where(Account.channel_id == channel_id)
                .where(Account.status == 'active')
            ) or 0,
            "pause": await session.scalar(
                async_select(func.count(Account.number))
                .where(Account.channel_id == channel_id)
                .where(Account.status == 'pause')
            ) or 0,
            "banned": await session.scalar(
                async_select(func.count(Account.number))
                .where(Account.channel_id == channel_id)
                .where(Account.status == 'ban')
            ) or 0,
            "total": await session.scalar(
                async_select(func.count(Account.number))
                .where(Account.channel_id == channel_id)
            ) or 0,
        }

        # Статистика активности за последние 24 часа
        yesterday = datetime.now() - timedelta(days=1)
        
        activity_stats = {
            "comments_24h": await session.scalar(
                async_select(func.sum(Account.comments_sent))
                .where(Account.channel_id == channel_id)
                .where(Account.last_activity >= yesterday)
            ) or 0,
            "likes_24h": await session.scalar(
                async_select(func.sum(Account.likes_given))
                .where(Account.channel_id == channel_id)
                .where(Account.last_activity >= yesterday)
            ) or 0,
            "total_comments": await session.scalar(
                async_select(func.sum(Account.comments_sent))
                .where(Account.channel_id == channel_id)
            ) or 0,
            "total_likes": await session.scalar(
                async_select(func.sum(Account.likes_given))
                .where(Account.channel_id == channel_id)
            ) or 0,
        }

        # Статистика по постам
        post_stats = {
            "total_posts": await session.scalar(
                async_select(func.count(PostActivity.id))
                .where(PostActivity.channel_name == channel.name)
            ) or 0,
            "posts_24h": await session.scalar(
                async_select(func.count(PostActivity.id))
                .where(PostActivity.channel_name == channel.name)
                .where(PostActivity.last_comment_time >= yesterday)
            ) or 0,
        }

        stats = {
            "channel_name": channel.name,
            **account_stats,
            **activity_stats,
            **post_stats
        }
    
    return {"stats": stats}


async def get_detailed_stats(dialog_manager: DialogManager, **kwargs):
    channel_id = dialog_manager.dialog_data.get("channel_id")
    if not channel_id:
        return {"detailed_stats": None}

    async with get_session() as session:
        channel = await session.get(Channel, channel_id)
        
        # Топ-5 самых активных аккаунтов по комментариям
        top_commenters = await session.execute(
            select(Account.number, Account.comments_sent, Account.likes_given, Account.last_activity)
            .where(Account.channel_id == channel_id)
            .order_by(Account.comments_sent.desc())
            .limit(5)
        )
        top_commenters = top_commenters.all()

        # Статистика по дням за последнюю неделю
        week_ago = datetime.now() - timedelta(days=7)
        daily_activity = []
        for i in range(7):
            day_start = week_ago + timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            
            day_comments = await session.scalar(
                async_select(func.count(CommentActivity.id))
                .where(CommentActivity.channel_name == channel.name)
                .where(and_(
                    CommentActivity.created_at >= day_start,
                    CommentActivity.created_at < day_end
                ))
            ) or 0
            
            daily_activity.append({
                "date": day_start.strftime("%d.%m"),
                "comments": day_comments
            })

        # Средняя активность
        avg_comments_per_day = sum(day["comments"] for day in daily_activity) / 7
        
        detailed_stats = {
            "channel_name": channel.name,
            "top_commenters": [
                {
                    "number": acc[0][-4:],  # Показываем только последние 4 цифры
                    "comments": acc[1],
                    "likes": acc[2],
                    "last_activity": acc[3].strftime("%d.%m %H:%M") if acc[3] else "Никогда"
                } for acc in top_commenters
            ],
            "daily_activity": daily_activity,
            "avg_comments_per_day": round(avg_comments_per_day, 1)
        }
    
    return {"detailed_stats": detailed_stats}


async def on_channel_selected(c: CallbackQuery, widget: Select, manager: DialogManager, item_id: str):
    manager.dialog_data["channel_id"] = int(item_id)
    await manager.switch_to(stats.show_stats)


async def on_refresh(c: CallbackQuery, button: Button, manager: DialogManager):
    data = await get_stats(manager)
    await manager.update(data)


async def on_detailed_stats(c: CallbackQuery, button: Button, manager: DialogManager):
    await manager.switch_to(stats.detailed_stats)


stats_dialog = Dialog(
    Window(
        Const("📊 Выберите канал для статистики:"),
        Select(
            Format("{item.name}"),
            id="s_channels",
            item_id_getter=lambda x: str(x.id),
            items="channels",
            on_click=on_channel_selected,
        ),
        Button(Const("НАЗАД"), on_click=on_click_back_main_menu, id='stats_back_button'),
        state=stats.channel_select,
        getter=get_channels
    ),
    Window(
        Format(
            "📈 <b>Статистика канала: {stats[channel_name]}</b>\n\n"
            "👥 <b>Аккаунты:</b>\n"
            "• ✅ Активных: {stats[active]}\n"
            "• ⏸ На паузе: {stats[pause]}\n"
            "• 🚫 Забанено: {stats[banned]}\n"
            "• 📊 Всего: {stats[total]}\n\n"
            "📝 <b>Активность за 24ч:</b>\n"
            "• 💬 Комментариев: {stats[comments_24h]}\n"
            "• 👍 Лайков: {stats[likes_24h]}\n\n"
            "📊 <b>Общая активность:</b>\n"
            "• 💬 Всего комментариев: {stats[total_comments]}\n"
            "• 👍 Всего лайков: {stats[total_likes]}\n"
            "• 📰 Постов обработано: {stats[total_posts]} (24ч: {stats[posts_24h]})"
        ),
        Button(Const("📋 Детальная статистика"), id="detailed", on_click=on_detailed_stats),
        Button(Const("🔄 Обновить"), id="refresh", on_click=on_refresh),
        Back(Const("🔙 Назад")),
        state=stats.show_stats,
        getter=get_stats
    ),
    Window(
        Format(
            "📋 <b>Детальная статистика: {detailed_stats[channel_name]}</b>\n\n"
            "🏆 <b>Топ-5 аккаунтов по активности:</b>\n"
            "{% for acc in detailed_stats[top_commenters] %}"
            "• {acc[number]}: {acc[comments]} комм, {acc[likes]} лайков (посл: {acc[last_activity]})\n"
            "{% endfor %}\n"
            "📅 <b>Активность по дням (комментарии):</b>\n"
            "{% for day in detailed_stats[daily_activity] %}"
            "• {day[date]}: {day[comments]} комм\n"
            "{% endfor %}\n"
            "📊 <b>Среднее за день:</b> {detailed_stats[avg_comments_per_day]} комм"
        ),
        Back(Const("🔙 Назад к общей статистике")),
        state=stats.detailed_stats,
        getter=get_detailed_stats
    )
)