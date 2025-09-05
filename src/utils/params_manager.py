from src.params.db_manager import DatabaseManager

async def init_default_params():
    db = DatabaseManager()
    defaults = {
        "comment_delay": "30",
        "comment_range": "10"
    }
    for key, value in defaults.items():
        if not await db.get_parameter(key):
            await db.set_parameter(key, value)