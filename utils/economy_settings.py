from motor.motor_asyncio import AsyncIOMotorClient
from utils.economy_db import settings

DEFAULT_COOLDOWNS = {
    "work": 10 * 60,
    "fish": 5 * 60,
    "rob": 60 * 60,
    "crime": 15 * 60,
    "bankrob": 2 * 60 * 60,
    "beg": 3 * 60,
}

async def get_guild_settings(guild_id: int):
    doc = await settings.find_one({"_id": guild_id})
    if not doc:
        doc = {
            "_id": guild_id,
            "cooldowns": DEFAULT_COOLDOWNS.copy()
        }
        await guild_settings.insert_one(doc)
    return doc


async def set_cooldown(guild_id: int, category: str, seconds: int):
    await settings.update_one(
        {"_id": guild_id},
        {"$set": {f"cooldowns.{category}": seconds}},
        upsert=True
    )


async def reset_guild_settings(guild_id: int):
    await settings.delete_one({"_id": guild_id})

async def get_cooldown(guild_id: int, key: str) -> int:
    data = await settings.find_one({"_id": guild_id}) or {}
    cooldowns = data.get("cooldowns", {})
    return cooldowns.get(key, DEFAULT_COOLDOWNS.get(key, 0))