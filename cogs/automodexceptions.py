import discord
from discord.ext import commands
from discord import app_commands
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

mongo = AsyncIOMotorClient(os.getenv("MONGO_URI"))
db = mongo["automod"]
exception_collection = db["exceptions"]


# ===== Embed生成関数 =====
async def build_exception_embed_for(bot: commands.Bot, guild_id: int, target_type: str, target_id: int, reset: bool = False):
    data = await exception_collection.find_one({"_id": f"{guild_id}-{target_type}-{target_id}"}) or {}

    checks = {
        "招待リンクの送信": data.get("invite", False),
        "詐欺サイトURLの送信": data.get("malicious_url", False),
        "NSFWサイトの送信": data.get("nsfw_url", False),
        "NGワードの送信": data.get("ng_word", False),
        "メッセージスパム": data.get("spam_message", False),
        "添付ファイルスパム": data.get("spam_attachment", False),
        "絵文字スパム": data.get("spam_emoji", False),
        "過剰改行の防止": data.get("spam_newline", False),
        "ログの記録": data.get("send_log", False)
    }

    lines = []
    for name, enabled in checks.items():
        # 「ログの記録」だけ逆に表示する
        if name == "ログの記録":
            emoji = "<:cross:1394240624202481705>" if enabled else "<:check:1394240622310850580>"
        else:
            emoji = "<:check:1394240622310850580>" if enabled else "<:cross:1394240624202481705>"
        lines.append(f"{emoji} {name}")


    guild = bot.get_guild(guild_id)
    if target_type == "channel":
        target_label = f"<#{target_id}>"
    else:
        member = guild.get_member(int(target_id)) if guild else None
        target_label = member.mention if member else f"<@{target_id}>"

    embed = discord.Embed(
        title=f"<:spanner:1399035839324880958> 例外設定",
        description=f"<:target:1431448531616530452>指定先:{target_label}",
        color=discord.Color.blurple()
    )
    embed.add_field(name="項目", value="\n".join(lines), inline=False)

    return embed


# ===== セレクトメニュー =====
class ExceptionSelect(discord.ui.Select):
    def __init__(self, parent_view, current_data: dict):
        self.parent_view = parent_view  # 親ビューを参照してボタン制御できるように
        options = [
            discord.SelectOption(label="招待リンクの送信", value="invite", emoji=discord.PartialEmoji(name="guildmemberAdd", id=1394238624786157649)),
            discord.SelectOption(label="詐欺サイトURLの送信", value="malicious_url", emoji=discord.PartialEmoji(name="skull", id=1430917423854387220)),
            discord.SelectOption(label="NSFWサイトの送信", value="nsfw_url", emoji=discord.PartialEmoji(name="nsfw", id=1398952436546273361)),
            discord.SelectOption(label="NGワードの送信", value="ng_word", emoji=discord.PartialEmoji(name="ngWords", id=1431294221532401776)),
            discord.SelectOption(label="メッセージスパム", value="spam_message", emoji=discord.PartialEmoji(name="spam", id=1431295206678069378)),
            discord.SelectOption(label="添付ファイルスパム", value="spam_attachment", emoji=discord.PartialEmoji(name="attachment", id=1430917487670726848)),
            discord.SelectOption(label="絵文字スパム", value="spam_emoji", emoji=discord.PartialEmoji(name="emojis", id=1401177044519223306)),
            discord.SelectOption(label="過剰改行の防止", value="spam_newline", emoji=discord.PartialEmoji(name="newline", id=1430917489143058432)),
            discord.SelectOption(label="ログの記録", value="send_log", emoji=discord.PartialEmoji(name="clipboard", id=1432725608651292762)),
        ]

        for opt in options:
            if current_data.get(opt.value, False):
                opt.default = True

        super().__init__(
            placeholder="例外にする項目を選択",
            min_values=0,
            max_values=len(options),
            options=options
        )
        # 現在の選択状態を記録（比較用）
        self.original_values = [k for k, v in current_data.items() if v]
        self.selected_values = self.original_values.copy()

    async def callback(self, interaction: discord.Interaction):
        self.selected_values = self.values

        is_changed = set(self.selected_values) != set(self.original_values)
        self.parent_view.save_button.disabled = not is_changed

        for opt in self.options:
            opt.default = opt.value in self.selected_values

        await interaction.response.edit_message(view=self.parent_view)




class ExceptionConfigView(discord.ui.View):
    def __init__(self, bot: commands.Bot, guild_id: int, target_type: str, target_id: int, current_data: dict, author_id: int):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.target_type = target_type
        self.target_id = target_id
        self.author_id = author_id

        self.select = ExceptionSelect(self, current_data)
        self.add_item(self.select)

        self.save_button = discord.ui.Button(
            label="保存",
            style=discord.ButtonStyle.success,
            emoji=discord.PartialEmoji(name="buttonSave", id=1431291252611219528),
            disabled=True
        )
        self.save_button.callback = self.save
        self.add_item(self.save_button)

        self.reset_button = discord.ui.Button(
            label="リセット",
            style=discord.ButtonStyle.danger,
            emoji=discord.PartialEmoji(name="buttonDelete", id=1431291664261058650)
        )
        self.reset_button.callback = self.reset
        self.add_item(self.reset_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            return False
        return True

    async def save(self, interaction: discord.Interaction):
        selected = set(self.select.selected_values)
        data = {key: (key in selected) for key in [
            "invite", "malicious_url", "nsfw_url", "ng_word",
            "spam_message", "spam_attachment", "spam_emoji", "spam_newline", "send_log"
        ]}

        await exception_collection.update_one(
            {"_id": f"{self.guild_id}-{self.target_type}-{self.target_id}"},
            {"$set": data},
            upsert=True
        )

        new_data = await exception_collection.find_one({"_id": f"{self.guild_id}-{self.target_type}-{self.target_id}"}) or {}
        new_view = ExceptionConfigView(self.bot, self.guild_id, self.target_type, self.target_id, new_data, self.author_id)
        embed = await build_exception_embed_for(self.bot, self.guild_id, self.target_type, self.target_id)

        await interaction.response.edit_message(embed=embed, view=new_view)

    async def reset(self, interaction: discord.Interaction):
        await exception_collection.delete_one({"_id": f"{self.guild_id}-{self.target_type}-{self.target_id}"})
        embed = await build_exception_embed_for(self.bot, self.guild_id, self.target_type, self.target_id, reset=True)

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)



# ===== Cog =====
class AutoModExceptions(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_group(name="exempt", description="例外設定を管理します。")
    @commands.has_permissions(manage_guild=True)
    async def exempt(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("使用方法: `z!exempt channel #チャンネル` または `z!exempt user @ユーザー`", ephemeral=True)

    @exempt.command(name="channel", description="指定したチャンネルの例外設定を変更します。")
    @app_commands.rename(channel="チャンネル")
    @commands.has_permissions(manage_guild=True)
    async def exempt_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        current_data = await exception_collection.find_one({"_id": f"{ctx.guild.id}-channel-{channel.id}"}) or {}
        embed = await build_exception_embed_for(self.bot, ctx.guild.id, "channel", channel.id)
        view = ExceptionConfigView(self.bot, ctx.guild.id, "channel", channel.id, current_data, author_id=ctx.author.id)
        await ctx.reply(embed=embed, view=view)

    @exempt.command(name="user", description="指定したユーザーの例外設定を変更します。")
    @app_commands.rename(user="ユーザー")
    @commands.has_permissions(manage_guild=True)
    async def exempt_user(self, ctx: commands.Context, user: discord.User):
        current_data = await exception_collection.find_one({"_id": f"{ctx.guild.id}-user-{user.id}"}) or {}
        embed = await build_exception_embed_for(self.bot, ctx.guild.id, "user", user.id)
        view = ExceptionConfigView(self.bot, ctx.guild.id, "user", user.id, current_data, author_id=ctx.author.id)
        await ctx.reply(embed=embed, view=view)

    @exempt.error
    async def exempt_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(f"<:cross:1394240624202481705> このコマンドを使うにはサーバー管理権限が必要です。", ephemeral=True)
    @exempt_channel.error
    async def exempt_channel_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(f"<:cross:1394240624202481705> このコマンドを使うにはサーバー管理権限が必要です。", ephemeral=True)
    @exempt_user.error
    async def exempt_user_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(f"<:cross:1394240624202481705> このコマンドを使うにはサーバー管理権限が必要です。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(AutoModExceptions(bot))
