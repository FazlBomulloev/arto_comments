from aiogram.types import CallbackQuery
from aiogram_dialog import DialogManager, ShowMode
from aiogram_dialog.widgets.kbd import Button
from ..states import menu


async def on_click_empty_func(call: CallbackQuery, button: Button,  manager: DialogManager):
    await call.answer(show_alert=True, text=f'''Простите, мы пока работаем над этим😓...''')

async def on_click_back_main_menu(c: CallbackQuery, button: Button, manager: DialogManager):
    await manager.start(state=menu.main_menu, show_mode=ShowMode.EDIT)