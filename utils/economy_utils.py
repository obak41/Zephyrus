import discord
from datetime import timezone, timedelta
from utils.economy_db import users

def format_coin(amount: int) -> str:
    return f"**<:coin:1434901953690865816>{amount:,}コイン**"


def create_embed(title: str = None, description: str = None, color=discord.Color.gold()):
    return discord.Embed(title=title, description=description, color=color, timestamp=discord.utils.utcnow())


def format_time(dt):
    """Discordのタイムスタンプ形式に変換"""
    if not dt:
        return "不明"
    
    # dt が UTC の datetime（discord.utils.utcnow()）ならそのままでOK
    timestamp = int(dt.timestamp()) + 32400
    return f"<t:{timestamp}:f>"

def paginate(data: list, per_page: int = 5):
    for i in range(0, len(data), per_page):
        yield data[i:i + per_page]

def normalize_inventory(data: dict) -> dict:
    """
    inventory が dict 以外だった場合でも
    安全に dict として扱えるようにする
    """
    inv = data.get("inventory")

    if isinstance(inv, dict):
        return inv

    # list / None / その他は空dict扱い
    return {}

async def inc_stat(guild_id: int, user_id: int, key: str, amount: int = 1):
    await users.update_one(
        {"_id": f"{guild_id}-{user_id}"},
        {"$inc": {f"stats.{key}": amount}},
        upsert=True
    )
