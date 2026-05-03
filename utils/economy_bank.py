import discord
from utils.economy_db import bank_rob_collection

async def get_bank_last_robbed(guild_id: int, bank_id: int) -> int | None:
    doc = await bank_rob_collection.find_one(
        {"_id": f"{guild_id}-{bank_id}"}
    )
    if not doc:
        return None
    return doc.get("last_robbed")


async def set_bank_last_robbed(guild_id: int, bank_id: int, ts: int):
    await bank_rob_collection.update_one(
        {"_id": f"{guild_id}-{bank_id}"},
        {"$set": {"last_robbed": ts}},
        upsert=True
    )

