from aiogram import Router
from src.interfaces.commands import router as commands_router
from .users.dialogs.menu import menu_dialog
from .users.dialogs.channels import channels_dialog
from .users.dialogs.channels_dialogs.add_agents import add_agent_dialog
from .users.dialogs.channels_dialogs.add_accounts import accounts_dialog
from .users.dialogs.settings import settings_dialog
from .users.dialogs.stats import stats_dialog

def get_all_routers() -> list[Router]:
    """Возвращает список всех роутеров для регистрации"""
    return[
        commands_router,
        menu_dialog,
        channels_dialog,
        add_agent_dialog,
        accounts_dialog,
        settings_dialog,
        stats_dialog
    ]