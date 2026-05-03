import discord
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

mongo_client = AsyncIOMotorClient(os.getenv("MONGO_URI"))
db = mongo_client["economy"]

users = db["users"]
logs = db["logs"]
shop = db["shop"]
bank_rob_collection = db["bank_rob_cooldowns"]
settings = db["settings"]
codes = db["redeem_code"]

async def get_code(code_str: str):
    """コードの情報を取得"""
    return await codes.find_one({"_id": code_str})

async def claim_code(code_str: str, user_id: int):
    """コードを使用済みに更新"""
    await codes.update_one(
        {"_id": code_str},
        {
            "$push": {"claimed_users": user_id}
        }
    )

async def update_inventory(guild_id, user_id, item_name, amount):
    await users.update_one(
        {"_id": f"{guild_id}-{user_id}"},
        {"$inc": {f"inventory.{item_name}": amount}},
        upsert=True
    )


async def get_user(guild_id: int, user_id: int):
    """ユーザーデータを取得 or 作成"""
    doc = await users.find_one({"_id": f"{guild_id}-{user_id}"})
    if not doc:
        doc = {
            "_id": f"{guild_id}-{user_id}",
            "wallet": 0,
            "bank": 0,
            "job": {
                "name": "サーバースタッフキャリア",
                "rank": 1,
                "worked": 0
            },
            "inventory": {},
            "cooldowns": {},
            "stats": {}
        }
        await users.insert_one(doc)
    return doc


async def update_balance(guild_id: int, user_id: int, wallet_delta: int = 0, bank_delta: int = 0):
    """ユーザー残高を更新"""
    await users.update_one(
        {"_id": f"{guild_id}-{user_id}"},
        {"$inc": {"wallet": wallet_delta, "bank": bank_delta}},
        upsert=True
    )


async def log_transaction(
    guild_id: int,
    actor_id: int,
    target_id: int,
    amount: int,
    detail: str,
    write_to: int = None  # 🔹どのユーザーに記録するか指定
):
    """
    取引ログを記録
    write_to:
        - None → 自動（target_id に記録）
        - user_id を指定 → そのユーザーのログに残す
    """
    log_user = write_to or target_id

    await logs.insert_one({
        "guild_id": guild_id,
        "log_user": log_user,  # 🔹ログ所有者（表示用）
        "actor_id": actor_id,  # 実行者（送金者など）
        "target_id": target_id,  # 対象（受け取り手など）
        "amount": amount,
        "detail": detail,
        "timestamp": discord.utils.utcnow()
    })


async def get_logs(guild_id: int, user_id: int, limit: int = 50):
    """指定ユーザーの取引履歴を取得"""
    cursor = logs.find({"guild_id": guild_id, "log_user": user_id}).sort("timestamp", -1).limit(limit)
    return await cursor.to_list(length=limit)

async def update_user_field(guild_id: int, user_id: int, field: str, value):
    await users.update_one(
        {"_id": f"{guild_id}-{user_id}"},
        {"$set": {field: value}}
    )
