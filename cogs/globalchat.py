import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import os
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient
from pathlib import Path
import io
import re

GLOBAL_MOD_GUILD_ID = 1393926423697428561
GLOBAL_MOD_ROLE_ID = 1393933376154636360

BANNED_REGEX = re.compile(
    r"@(?:everyone|here)"
    r"|\b[A-Za-z0-9]{23,40}\.[A-Za-z0-9]{5,10}\.[A-Za-z0-9\-]{20,40}\b"
    r"|discord\.(?:gg|com/invite)"
    r"|(https?:\/\/)?imgur\.com",
    re.IGNORECASE
)

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
WEBHOOK_ICON = ASSETS_DIR / "webhook_icon.png"

load_dotenv()
mongo_client = AsyncIOMotorClient(os.getenv("MONGO_URI"))
db = mongo_client["globalchat"]
collection = db["channels"]
messages = db["messages"]
bans = db["bans"]
message_index = db["message_index"]

async def build_reply_block(
    messages_col,
    reply_to_global: str | None,
    target_key: str
) -> str:
    if not reply_to_global:
        return ""

    parent = await messages_col.find_one({"_id": reply_to_global})
    if not parent:
        return ""

    # 表示名（なければフォールバック）
    author_name = parent.get("author_name", "不明なユーザー")

    # Webhook版を優先
    target_id = parent["messages"].get(target_key)

    guild_id, channel_id = map(int, target_key.split("-"))

    # 無ければ origin
    if not target_id:
        origin = parent.get("origin")
        if origin:
            target_id = origin["message_id"]

    if not target_id:
        return f"┏返信先：{author_name}\n"

    jump = make_jump_url(guild_id, channel_id, target_id)
    return f"┏[返信先：{author_name}]({jump})\n"

def build_join_embed(guild: discord.Guild) -> discord.Embed:
    embed = discord.Embed(
        color=discord.Color.green()
    )

    guild_icon_url = None
    if guild.icon:
        guild_icon_url = guild.icon.url

    embed.set_author(name=f"{guild.name}(ID: {guild.id})がグローバルチャットに参加しました！", icon_url=guild_icon_url)
    return embed

class GlobalEmoji:
    SENDING = 1457731384746442845
    SUCCESS = 1394240622310850580
    PARTIAL = 1394241229176311888
    FAILED  = 1394240624202481705
    BANNED  = 1457734791838306399

async def add_reaction_safe(bot: commands.Bot, msg: discord.Message, emoji_id: int):
    emoji = bot.get_emoji(emoji_id)
    if not emoji:
        return

    try:
        await msg.add_reaction(emoji)
    except discord.Forbidden:
        pass

async def remove_reaction_later(
    bot: commands.Bot,
    message: discord.Message,
    emoji_id: int,
    delay: int = 10
):
    await asyncio.sleep(delay)

    emoji = bot.get_emoji(emoji_id)
    if not emoji:
        return

    try:
        await message.remove_reaction(emoji, message.guild.me)
    except (discord.NotFound, discord.Forbidden):
        pass

def has_global_mod_permission(bot: discord.Client, user: discord.User) -> bool:
    guild = bot.get_guild(GLOBAL_MOD_GUILD_ID)
    if not guild:
        return False

    member = guild.get_member(user.id)
    if not member:
        return False

    return any(role.id == GLOBAL_MOD_ROLE_ID for role in member.roles)

def make_jump_url(guild_id: int, channel_id: int, message_id: int) -> str:
    return f"https://discord.com/channels/{guild_id}/{channel_id}/{message_id}"

class GlobalChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.messages = messages
        self.collection = collection
        self.bans = bans
        self.message_index = message_index

    async def is_globally_banned(self, user_id: int) -> bool:
        return await bans.find_one({"_id": user_id}) is not None

    async def get_webhook(self, guild_id: int, channel_id: int) -> discord.Webhook:
        data = await collection.find_one(
            {"_id": f"{guild_id}-{channel_id}"}
        )
        if not data:
            raise RuntimeError("Webhook data not found")

        return discord.Webhook.from_url(
            data["webhook_url"],
            client=self.bot
        )

    # =====================
    # /globalchat
    # =====================
    @commands.hybrid_group(name="globalchat")
    async def globalchat(self, ctx):
        pass
    @globalchat.command(name="join", description="グローバルチャットに参加します。")
    @commands.has_permissions(manage_channels=True)
    async def join(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        channel_id = ctx.channel.id

        # 🔍 すでにこのサーバーで参加中のチャンネルを探す
        old = await collection.find_one({"guild_id": guild_id})

        if old:
            # 既存 Webhook 削除
            try:
                old_webhook = discord.Webhook.from_url(
                    old["webhook_url"],
                    client=self.bot
                )
                await old_webhook.delete()
            except discord.NotFound:
                pass  # 既に消されていてもOK

            await collection.delete_one({"_id": old["_id"]})

            await ctx.send(
                f"<:check:1394240622310850580> 既存のグローバルチャットチャンネル "
                f"(<#{old['channel_id']}>) を解除しました。"
            )

        avatar_bytes = None
        if WEBHOOK_ICON.exists():
            with open(WEBHOOK_ICON, "rb") as f:
                avatar_bytes = f.read()

        # 🆕 新しい Webhook 作成
        webhook = await ctx.channel.create_webhook(name="Zephyrus GlobalChat", avatar=avatar_bytes)

        await collection.insert_one({
            "_id": f"{guild_id}-{channel_id}",
            "guild_id": guild_id,
            "channel_id": channel_id,
            "webhook_url": webhook.url
        })

        await ctx.reply(
            "<:check:1394240622310850580> グローバルチャットに参加しました。"
        )

        # ============================
        # 🌐 他サーバーへ参加通知
        # ============================
        embed = build_join_embed(ctx.guild)

        async for ch in collection.find():
            target_key = ch["_id"]

            # 自分のサーバーには送らない
            if target_key == f"{guild_id}-{channel_id}":
                continue

            try:
                wh = discord.Webhook.from_url(
                    ch["webhook_url"],
                    client=self.bot
                )

                await wh.send(
                    embed=embed
                )

            except discord.NotFound:
                await collection.delete_one({"_id": target_key})
            except discord.Forbidden:
                pass
            except Exception as e:
                print(f"[GlobalChat] 参加通知送信失敗({target_key}): {e}")

    @globalchat.command(name="leave", description="グローバルチャットから退出します。")
    @commands.has_permissions(manage_channels=True)
    async def leave(self, ctx):
        data = await collection.find_one(
            {"_id": f"{ctx.guild.id}-{ctx.channel.id}"}
        )
        if not data:
            return await ctx.reply("<:warn:1394241229176311888> このチャンネルは参加していません。")

        webhook = discord.Webhook.from_url(
            data["webhook_url"],
            client=self.bot
        )
        await webhook.delete()

        await collection.delete_one({"_id": data["_id"]})
        await ctx.reply("<:check:1394240622310850580> グローバルチャットから退出しました。")

    @globalchat.command(name="ban", description="ユーザーをグローバルチャットからBANします。")
    @app_commands.rename(user="ユーザー", reason="理由")
    async def globalchat_ban(
        self,
        ctx: commands.Context,
        user: discord.User,
        reason: str | None = None
    ):
        # 🔒 権限チェック
        if not has_global_mod_permission(ctx.bot, ctx.author):
            return await ctx.reply(
                "<:cross:1394240624202481705> このコマンドを実行する権限がありません。",
                ephemeral=True
            )

        if user.bot:
            return await ctx.reply(
                "<:warn:1394241229176311888> botはBANできません。",
                ephemeral=True
            )

        if user.id == ctx.author.id:
            return await ctx.reply(
                "自分自身はBANできません。",
                ephemeral=True
            )

        if user.id == self.bot.owner_id:
            return await ctx.reply(
                "bot所有者はBANできません。",
                ephemeral=True
            )

        if await bans.find_one({"_id": user.id}):
            return await ctx.reply(
                "<:warn:1394241229176311888> そのユーザーはすでにBANされています。",
                ephemeral=True
            )

        await bans.insert_one({
            "_id": user.id,
            "reason": reason or "理由なし",
            "banned_by": ctx.author.id,
            "timestamp": discord.utils.utcnow()
        })

        await ctx.reply(
            f"<:check:1394240622310850580> {user.mention} をグローバルチャットからBANしました。",
            ephemeral=True
        )

    @globalchat.command(name="unban", description="グローバルチャットからのBANを解除します。")
    @app_commands.rename(user="ユーザー")
    async def globalchat_unban(
        self,
        ctx: commands.Context,
        user: discord.User
    ):
        # 🔒 権限チェック
        if not has_global_mod_permission(ctx.bot, ctx.author):
            return await ctx.reply(
                "<:cross:1394240624202481705> このコマンドを実行する権限がありません。",
                ephemeral=True
            )

        result = await bans.delete_one({"_id": user.id})

        if result.deleted_count == 0:
            return await ctx.reply(
                "<:warn:1394241229176311888> そのユーザーはBANされていません。",
                ephemeral=True
            )

        await ctx.reply(
            f"<:check:1394240622310850580> {user.mention}のBANを解除しました。",
            ephemeral=True
        )

    @join.error
    async def join_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(f"<:cross:1394240624202481705> このコマンドを使うにはチャンネルの管理権限が必要です。", ephemeral=True)

    @leave.error
    async def leave_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(f"<:cross:1394240624202481705> このコマンドを使うにはサーバー管理権限が必要です。", ephemeral=True)
            
    # =====================
    # メッセージ中継
    # =====================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        key = f"{message.guild.id}-{message.channel.id}"
        if not await collection.find_one({"_id": key}):
            return

        # 🚫 グローバルBAN
        if await self.is_globally_banned(message.author.id):
            print(f"Emoji ID:{GlobalEmoji.BANNED}")
            await add_reaction_safe(self.bot, message, GlobalEmoji.BANNED)
            return

        if BANNED_REGEX.search(message.content):
            await add_reaction_safe(self.bot, message, GlobalEmoji.BANNED)
            return

        # 🔄 送信中リアクション
        await add_reaction_safe(self.bot, message, GlobalEmoji.SENDING)

        # =====================
        # 🔁 返信元グローバルID取得
        # =====================
        reply_to_global = None

        if message.reference and isinstance(message.reference.resolved, discord.Message):
            ref = message.reference.resolved

            index = await self.message_index.find_one({"_id": ref.id})
            if index:
                # Webhookメッセージ → origin を使う
                reply_to_global = index["origin_id"]
            else:
                # ★ 送信元サーバーの元メッセージ
                reply_to_global = str(ref.id)

        attachment_bytes = []

        for a in message.attachments:
            data = await a.read()
            attachment_bytes.append((a.filename, data))


        MAX_RETRY = 3
        success = 0
        failed_channels = []
        message_map = {}

        # =====================
        # 送信
        # =====================
        async for ch in collection.find():
            target_key = ch["_id"]

            if target_key == key:
                continue

            reply_block = await build_reply_block(
                self.messages,
                reply_to_global,
                target_key
            )

            base_text = (
                f"{reply_block}"
                f"{message.content}\n"
                f"-# 元メッセージID:{message.id}"
            )

            try:
                webhook = discord.Webhook.from_url(
                    ch["webhook_url"],
                    client=self.bot
                )

                files = [
                    discord.File(fp=io.BytesIO(data), filename=filename)
                    for filename, data in attachment_bytes
                ]

                sent = await webhook.send(
                    content=base_text,
                    username=f"{message.author.display_name}(@{message.author.name} - {message.author.id})",
                    avatar_url=message.author.display_avatar.url,
                    files=files,
                    wait=True
                )

                await message_index.insert_one({
                    "_id": sent.id,
                    "origin_id": str(message.id)
                })

                message_map[target_key] = sent.id
                success += 1

            except discord.NotFound:
                # Webhookが消されている
                await collection.delete_one({"_id": target_key})

            except discord.Forbidden:
                # 権限不足（ログ残してもいい）
                failed_channels.append(ch)

            except Exception as e:
                # 想定外はログに出す
                print(f"[GlobalChat]送信失敗(Target Key:{target_key}): {e}")
                failed_channels.append(ch)

        # =====================
        # 🔁 再送
        # =====================
        for _ in range(MAX_RETRY):
            if not failed_channels:
                break

            await asyncio.sleep(1.5)
            retry = failed_channels
            failed_channels = []

            for ch in retry:
                target_key = ch["_id"]

                reply_block = await build_reply_block(
                    self.messages,
                    reply_to_global,
                    target_key
                )

                if target_key == key:
                    continue


                # ===== base_text（送信先ごと）=====
                base_text = (
                    f"{reply_block}"
                    f"{message.content}\n"
                    f"-# 元メッセージID:{message.id}"
                )

                try:
                    webhook = discord.Webhook.from_url(
                        ch["webhook_url"],
                        client=self.bot
                    )

                    files = [
                        discord.File(fp=io.BytesIO(data), filename=filename)
                        for filename, data in attachment_bytes
                    ]

                    sent = await webhook.send(
                        content=base_text,
                        username=message.author.display_name,
                        avatar_url=message.author.display_avatar.url,
                        files=files,
                        wait=True
                    )

                    await message_index.insert_one({
                        "_id": sent.id,           # ← WebhookメッセージID
                        "origin_id": str(message.id)
                    })

                    success += 1
                    message_map[ch["_id"]] = sent.id

                except discord.NotFound:
                    await collection.delete_one({"_id": ch["_id"]})

                except Exception:
                    failed_channels.append(ch)

        # =====================
        # 💾 保存
        # =====================
        if message_map:
            await messages.insert_one({
                "_id": str(message.id),
                "author_id": message.author.id,
                "author_name": message.author.display_name,  # ★ 追加
                "origin": {
                    "guild_id": message.guild.id,
                    "channel_id": message.channel.id,
                    "message_id": message.id
                },
                "messages": message_map,
                "reply_to": reply_to_global
            })


        # =====================
        # ✅ リアクション
        # =====================
        sending = self.bot.get_emoji(GlobalEmoji.SENDING)
        if sending:
            await message.clear_reaction(sending)
        if success > 0 and not failed_channels:
            await add_reaction_safe(self.bot, message, GlobalEmoji.SUCCESS)
            asyncio.create_task(remove_reaction_later(self.bot, message, GlobalEmoji.SUCCESS, 10))
        elif success > 0:
            await add_reaction_safe(self.bot, message, GlobalEmoji.PARTIAL)
        else:
            await add_reaction_safe(self.bot, message, GlobalEmoji.FAILED)
    
    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.content == after.content:
            return

        data = await self.messages.find_one({"_id": str(before.id)})
        if not data:
            return

        if BANNED_REGEX.search(after.content):
            await add_reaction_safe(self.bot, after, GlobalEmoji.BANNED)
            return
        
        reply_to = data.get("reply_to")

        for key, msg_id in data["messages"].items():
            guild_id, channel_id = map(int, key.split("-"))
            webhook = await self.get_webhook(guild_id, channel_id)

            reply_block = await build_reply_block(
                self.messages,
                reply_to,
                key
            )

            new_content = (
                f"{reply_block}"
                f"{after.content}\n"
                f"-# 元メッセージID:{before.id}"
            )

            await webhook.edit_message(
                msg_id,
                content=new_content
            )

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        data = await messages.find_one({"_id": str(message.id)})
        if not data:
            return

        for key, msg_id in data["messages"].items():
            guild_id, channel_id = map(int, key.split("-"))
            webhook = await self.get_webhook(guild_id, channel_id)
            await webhook.delete_message(msg_id)

        await messages.delete_one({"_id": str(message.id)})
        await message_index.delete_many({"origin_id": str(message.id)})
    
@app_commands.context_menu(name="グローバルメッセージを削除")
async def delete_global_message(
    interaction: discord.Interaction,
    message: discord.Message
):
    bot = interaction.client

    # 🔒 権限チェック
    if not has_global_mod_permission(bot, interaction.user):
        return await interaction.response.send_message(
            "<:cross:1394240624202481705> この操作を行う権限がありません。",
            ephemeral=True
        )

    cog: GlobalChat | None = bot.get_cog("GlobalChat")
    if not cog:
        return await interaction.response.send_message(
            "GlobalChat がロードされていません。",
            ephemeral=True
        )

    index = await cog.message_index.find_one(
        {"_id": message.id}
    )

    if not index:
        return await interaction.response.send_message(
            "<:warn:1394241229176311888> このメッセージはグローバルチャットのものではありません。",
            ephemeral=True
        )

    origin_id = index["origin_id"]
    data = await cog.messages.find_one({"_id": origin_id})

    # === グローバル側削除 ===
    for key, msg_id in data["messages"].items():
        guild_id, channel_id = map(int, key.split("-"))
        webhook = await cog.get_webhook(guild_id, channel_id)
        await webhook.delete_message(msg_id)

    # === 元メッセージ削除 ===
    origin_guild = interaction.guild
    origin_channel = message.channel

    try:
        await message.delete()
    except (discord.Forbidden, discord.NotFound):
        pass

    # === DB掃除 ===
    await cog.message_index.delete_many({"origin_id": origin_id})
    await cog.messages.delete_one({"_id": origin_id})

    await interaction.response.send_message(
        "<:check:1394240622310850580> グローバルメッセージを削除しました。",
        ephemeral=True
    )

async def setup(bot):
    await bot.add_cog(GlobalChat(bot))
    bot.tree.add_command(delete_global_message)