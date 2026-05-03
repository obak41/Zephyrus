import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

# =====================
# MongoDB
# =====================
load_dotenv()
mongo = AsyncIOMotorClient(os.getenv("MONGO_URI"))
db = mongo["autokick"]
log_db = mongo["serverlog"]

cfg_col = db["config"]
whitelist_col = db["whitelist"]
log_col = log_db["channel.serverlog.channel"]

# =====================
# 判定関数
# =====================
def is_no_avatar(member: discord.Member) -> bool:
    return member.avatar is None

def is_new_account(member: discord.Member, days: int) -> bool:
    return (discord.utils.utcnow() - member.created_at) < timedelta(days=days)

def is_unverified_bot(member: discord.Member) -> bool:
    return member.bot and not member.public_flags.verified_bot

class WhitelistConfigView(discord.ui.View):
    def __init__(self, guild: discord.Guild, user_id: int):
        super().__init__(timeout=None)
        self.guild = guild
        self.user_id = user_id
        self.message: discord.Message | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            return False
        return True

    async def build_embed(self) -> discord.Embed:
        cfg = await whitelist_col.find_one({"_id": self.guild.id}) or {}
        users = cfg.get("users", [])

        if users:
            lines = []
            for uid in users:
                member = self.guild.get_member(uid)
                lines.append(member.mention if member else f"<@{uid}>")
            value = "\n".join(lines)
        else:
            value = "なし"

        embed = discord.Embed(
            title="<:spanner:1399035839324880958>ホワイトリスト設定パネル",
            description=f"**登録ユーザー一覧**\n{value}",
            color=discord.Color.dark_gray()
        )
        return embed

    async def refresh(self, interaction: discord.Interaction | None = None):
        embed = await self.build_embed()

        if interaction:
            await interaction.response.edit_message(embed=embed, view=self)
        elif self.message:
            await self.message.edit(embed=embed, view=self)

    @discord.ui.button(
        label="削除",
        style=discord.ButtonStyle.red,
        emoji="<:buttonMinus:1444665078015066182>"
    )
    async def remove_user(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        cfg = await whitelist_col.find_one({"_id": self.guild.id}) or {}
        users = cfg.get("users", [])

        if not users:
            await interaction.response.send_message(
                "<:warn:1394241229176311888> ホワイトリストは空です。",
                ephemeral=True
            )
            return

        options = []
        for uid in users:
            member = self.guild.get_member(uid)
            label = member.display_name if member else f"User ID: {uid}"
            options.append(discord.SelectOption(label=label, value=str(uid)))

        select = discord.ui.Select(
            placeholder="削除するユーザーを選択",
            options=options
        )

        async def select_callback(select_interaction: discord.Interaction):
            target_id = int(select.values[0])

            await whitelist_col.update_one(
                {"_id": self.guild.id},
                {"$pull": {"users": target_id}}
            )

            await select_interaction.response.send_message(
                f"<:check:1394240622310850580> <@{target_id}> を削除しました。",
                ephemeral=True
            )

            await self.refresh()

        select.callback = select_callback

        view = discord.ui.View()
        view.add_item(select)

        await interaction.response.send_message(
            "削除するユーザーを選んでください。",
            view=view,
            ephemeral=True
        )

# =====================
# 許可ボタン
# =====================
class AllowJoinView(discord.ui.View):
    def __init__(self, member_id: int):
        super().__init__(timeout=None)
        self.member_id = member_id

    @discord.ui.button(
        label="参加を許可",
        style=discord.ButtonStyle.success,
    )
    async def allow(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.kick_members:
            return await interaction.response.send_message(
                "<:cross:1394240624202481705> この操作を行う権限がありません。",
                ephemeral=True
            )

        # --- DB更新 ---
        await whitelist_col.update_one(
            {"_id": interaction.guild.id},
            {"$addToSet": {"users": self.member_id}},
            upsert=True
        )

        # --- ボタンを無効化＆ラベル変更 ---
        button.label = "参加を許可しました"
        button.style = discord.ButtonStyle.secondary
        button.disabled = True

        # --- メッセージを更新 ---
        await interaction.response.edit_message(view=self)


# =====================
# Cog
# =====================
class AutoKick(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -----------------
    # 設定取得
    # -----------------
    async def get_config(self, guild_id: int):
        cfg = await cfg_col.find_one({"_id": guild_id})
        if not cfg:
            cfg = {
                "_id": guild_id,
                "enabled": False,
                "modes": {
                    "suspicious": False,
                    "noavatar": False,
                    "bot": False
                },
                "account_age_days": 7
            }
            await cfg_col.insert_one(cfg)
        return cfg

    # -----------------
    # on_member_join
    # -----------------
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        cfg = await self.get_config(member.guild.id)
        if not cfg["enabled"]:
            return

        wl = await whitelist_col.find_one({"_id": member.guild.id}) or {}
        if member.id in wl.get("users", []) or member.id in wl.get("bots", []):
            return

        reason = None

        # ① 未認証Bot
        if cfg["modes"]["bot"] and is_unverified_bot(member):
            reason = "未認証bot"

        # ② アバターなし
        elif cfg["modes"]["noavatar"] and is_no_avatar(member):
            reason = "アバターのないアカウント"

        # ③ 不審なアカウント
        elif cfg["modes"]["suspicious"]:
            if is_new_account(member, cfg["account_age_days"]):
                reason = "不審なアカウント"

        if not reason:
            return

        # DM
        if member.bot:
            dm_sent = False
            dm_reason = "\n<:space:1416299781869015081><:rightSort:1401174996574801950>理由:botアカウント"
        else:
            dm_sent = True
            dm_reason = ""
            embed = discord.Embed(
                description=(f"<:rightSort:1401174996574801950>理由:{reason}")
            )
            embed.set_author(name=f"あなたは {member.guild.name} からキックされました。", icon_url=member.guild.icon.url)
            try:
                await member.send(embed=embed)
            except discord.Forbidden:
                dm_sent = False
                dm_reason = "\n<:space:1416299781869015081><:rightSort:1401174996574801950>理由:受信拒否"
                pass

        # ログ
        await self.send_log(member, reason, dm_sent, dm_reason)

        await member.kick(reason=reason)

    # -----------------
    # ログ送信
    # -----------------
    async def send_log(self, member: discord.Member, reason: str, dm_sent: bool, dm_reason: str):
        embed = discord.Embed(
            description=(
                f"**<:guildMemberRemove:1394238635653464104>{member.mention} をキックしました。**\n"
                f"<:space:1416299781869015081><:rightSort:1401174996574801950>理由:{reason}\n**詳細**\n"
                f"<:dm:1462442627407544472>DMの送信:{'はい' if dm_sent else 'いいえ'}{dm_reason}"
            ),
            color=discord.Color.yellow(),
            timestamp=discord.utils.utcnow()
        )

        embed.set_author(name=member, icon_url=member.display_avatar.url)
        embed.set_footer(text=f"ユーザーID:{member.id}")
        
        log_data = await log_col.find_one({"_id": member.guild.id})
        if not log_data:
            return

        channel_id = log_data.get("log_channel_id")
        if not channel_id:
            return

        log_ch = member.guild.get_channel(channel_id)
        if not log_ch:
            return
        
        await log_ch.send(
            embed=embed,
            view=AllowJoinView(member.id)
        )

    # =====================
    # /autokick
    # =====================
    @commands.hybrid_group(name="autokick", aliases=["ak"])
    @commands.has_permissions(manage_guild=True)
    async def autokick(self, ctx):
        pass

    @autokick.command(name="suspicious", description="不審なアカウントを自動でキックします。", aliases=["sus"])
    @app_commands.rename(enabled="有効", days="作成からの日数")
    async def suspicious(self, ctx: commands.Context, enabled: bool, days: int | None = None):
        update = {
            "enabled": True,
            "modes.suspicious": enabled
        }

        if days is not None:
            if days < 1:
                return await ctx.reply(
                    "<:warn:1394241229176311888> 日数は1以上を指定してください。",
                    ephemeral=True
                )
            update["account_age_days"] = days
            date = days
        else:
            update["account_age_days"] = 7
            date = 7

        await cfg_col.update_one(
            {"_id": ctx.guild.id},
            {"$set": update},
            upsert=True
        )

        msg = f"オートキック(不審なアカウント)を{'有効' if enabled else '無効'}にしました。"
        if enabled is True:
            msg += f"\n判定基準: アカウント作成から **{date}日以内**"

        await ctx.reply(msg)

    @autokick.command(name="noavatar", description="アバターのないアカウントを自動でキックします。")
    @app_commands.rename(enabled="有効")
    async def noavatar(self, ctx, enabled: bool):
        await cfg_col.update_one(
            {"_id": ctx.guild.id},
            {"$set": {"enabled": True, "modes.noavatar": enabled}},
            upsert=True
        )
        await ctx.reply(f"オートキック(アバターのないアカウント)を{'有効' if enabled else '無効'}にしました。")

    @autokick.command(name="bot", description="未認証botを自動でキックします。")
    @app_commands.rename(enabled="有効")
    async def bot(self, ctx, enabled: bool):
        await cfg_col.update_one(
            {"_id": ctx.guild.id},
            {"$set": {"enabled": True, "modes.bot": enabled}},
            upsert=True
        )
        await ctx.reply(f"オートキック(未認証bot)を{'有効' if enabled else '無効'}にしました。")

    @autokick.command(name="whitelist", description="参加を許可するユーザーを表示します。", aliases=["w"])
    @commands.has_permissions(manage_guild=True)
    async def whitelist(self, ctx: commands.Context):
        view = WhitelistConfigView(ctx.guild, ctx.author.id)
        embed = await view.build_embed()

        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

# =====================
# setup
# =====================
async def setup(bot):
    await bot.add_cog(AutoKick(bot))
