import time
from utils.economy_db import users, get_user, update_user_field
from utils.economy_settings import get_guild_settings
from utils.economy_settings import get_cooldown

async def check_cooldown(guild_id: int, user_id: int, key: str):
    user = await get_user(guild_id, user_id)
    cooldowns = user.get("cooldowns", {})

    now = int(time.time())
    expires = cooldowns.get(key)

    if expires is not None:
        try:
            expires = int(expires)
        except (ValueError, TypeError):
            expires = None

    # クールダウン切れ or 未設定
    if not expires or expires <= now:
        cooldown_seconds = await get_cooldown(guild_id, key)
        if cooldown_seconds > 0:
            cooldowns[key] = now + cooldown_seconds
            await update_user_field(guild_id, user_id, "cooldowns", cooldowns)
        return True, 0

    # クールダウン中
    remain = expires - now
    return False, remain
