from discord.ext import commands
from discord import app_commands
import discord
import json
import os
from pathlib import Path
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

CONFIG_PATH = Path("ai_config/active_channels.json")
HISTORY_PATH = Path("ai_config/history.json")

def save_active_channels(channels: dict[int, dict]):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({str(cid): True for cid in channels}, f, indent=2)

def load_active_channels() -> dict[int, dict]:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return {int(cid): {} for cid in data.keys()}
    return {}

def save_history(history: dict):
    with open(HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

def load_history() -> dict:
    if HISTORY_PATH.exists():
        with open(HISTORY_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

class AIChat(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.ai_channels = load_active_channels()
        self.histories = load_history()

    # グループスラッシュコマンド定義
    ai_group = app_commands.Group(name="aichat", description="AIチャットの設定を行います。")

    @ai_group.command(name="enable", description="指定したチャンネルでAIチャットを有効化します。")
    @app_commands.describe(channel="設定したいチャンネル")
    @app_commands.rename(channel="チャンネル")
    async def enable(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                "<:cross:1394240624202481705>このコマンドを実行するにはチャンネル管理権限が必要です。",
                ephemeral=True
            )
        self.ai_channels[channel.id] = {}
        save_active_channels(self.ai_channels)
        await interaction.response.send_message(f"<:check:1394240622310850580>AIチャットを {channel.mention} で有効化しました。", ephemeral=True)

    @ai_group.command(name="disable", description="このチャンネルでのAIチャットを無効化します。")
    async def disable(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                "<:cross:1394240624202481705>このコマンドを実行するにはチャンネル管理権限が必要です。",
                ephemeral=True
            )
        channel_id = interaction.channel.id
        if channel_id in self.ai_channels:
            del self.ai_channels[channel_id]
            save_active_channels(self.ai_channels)
            await interaction.response.send_message("<:check:1394240622310850580>このチャンネルでのAIチャットを無効化しました。", ephemeral=True)
        else:
            await interaction.response.send_message("<:warn:1394241229176311888>このチャンネルではAIチャットは有効化されていません。", ephemeral=True)

    @commands.group(name="aichat", invoke_without_command=True)
    async def aichat(self, ctx: commands.Context):
        await ctx.send("使用方法: `zd!aichat enable #チャンネル` または `zd!aichat disable`")

    @aichat.command(name="enable")
    @commands.has_permissions(manage_channels=True)
    async def aichat_enable(self, ctx: commands.Context, channel: discord.TextChannel):
        self.ai_channels[channel.id] = {}
        save_active_channels(self.ai_channels)
        await ctx.send(f"<:check:1394240622310850580>AIチャットを <#{channel.id}> で有効化しました。")

    @aichat.command(name="disable")
    @commands.has_permissions(manage_channels=True)
    async def aichat_disable(self, ctx: commands.Context):
        channel_id = ctx.channel.id
        if channel_id in self.ai_channels:
            del self.ai_channels[channel_id]
            save_active_channels(self.ai_channels)
            await ctx.send("<:check:1394240622310850580>このチャンネルでのAIチャットを無効化しました。")
        else:
            await ctx.send("<:warn:1394241229176311888>このチャンネルではAIチャットは有効化されていません。")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        ctx = await self.bot.get_context(message)
        if ctx.command is not None:
            return

        channel_id = message.channel.id
        user_id = str(message.author.id)

        if channel_id in self.ai_channels:
            if channel_id not in self.histories:
                self.histories[channel_id] = {}

            if user_id not in self.histories[channel_id]:
                self.histories[channel_id][user_id] = []

            history = self.histories[channel_id][user_id]
            model = genai.GenerativeModel("gemini-2.0-flash")
            session = model.start_chat(history=history)

            async with message.channel.typing():
                try:
                    content_parts = [message.content]
                    if message.attachments:
                        image_attachments = [att for att in message.attachments if att.content_type and att.content_type.startswith("image/")]
                        if image_attachments:
                            image_datas = [await att.read() for att in image_attachments]
                            uploaded_images = [genai.upload_image(img) for img in image_datas]
                            content_parts.extend(uploaded_images)

                    response = await self.bot.loop.run_in_executor(
                        None,
                        lambda: session.send_message(content_parts)
                    )

                    history.append({"role": "user", "parts": [message.content]})
                    history.append({"role": "model", "parts": [response.text]})
                    save_history(self.histories)
                    await message.channel.reply(response.text)
                except Exception as e:
                    await message.channel.reply(f"<:warn:1394241229176311888>エラーが発生しました: {e}")

        await self.bot.process_commands(message)

async def setup(bot):
    await bot.add_cog(AIChat(bot))
