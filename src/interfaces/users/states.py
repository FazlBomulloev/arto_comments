from aiogram.fsm.state import State, StatesGroup

class menu(StatesGroup):
    main_menu=State()

class channels(StatesGroup):
    main_menu = State()
    channel_menu = State()
    add_channel = State()
    confirm_channel = State()
    enter_channel_username = State()
    enter_invite_link = State()
    upload_list = State()
    edit_param = State()
    upload_photos = State()
    # Новые состояния для переноса аккаунтов
    transfer_select_channel = State()
    transfer_enter_count = State()
    transfer_confirm = State()

class settings(StatesGroup):
    main_menu=State()
    param_input = State()

class accounts(StatesGroup):
    wait_zip_file = State()
    processing_zip = State()
    show_results = State()

class agents(StatesGroup):
    select_agent = State()
    agent_info = State()
    enter_api_id = State()
    enter_description = State()
    confirm_agent = State()

class stats(StatesGroup):
    channel_select = State()
    show_stats = State()
    detailed_stats = State()