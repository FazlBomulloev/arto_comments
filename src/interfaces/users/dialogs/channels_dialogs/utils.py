from aiogram.types import CallbackQuery
from aiogram_dialog import DialogManager, ShowMode
from aiogram_dialog.widgets.kbd import Button

from src.interfaces.users.states import channels


async def on_back_channel_menu(c: CallbackQuery, button: Button, manager: DialogManager):
    # Получаем channel_id из start_data или dialog_data
    channel_id = manager.dialog_data.get("channel_id")
    if not channel_id:
        await manager.done()
        return
    await manager.start(
        state=channels.channel_menu,
        data={"channel_id": channel_id},
        show_mode=ShowMode.EDIT
    )
