from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from aiogram_dialog import DialogManager, StartMode
from .users.states import channels

from src.interfaces.users.states import menu
from src.db.pool_manager import get_session
from sqlalchemy import select

from src.cfg import config

router = Router()

@router.message(Command("start"))
async def start(message: Message, dialog_manager: DialogManager):
    if str(message.from_user.id) in config.ADMIN_LIST:
        await dialog_manager.start(
            state=menu.main_menu,
            mode=StartMode.RESET_STACK
        )
    else:
        pass