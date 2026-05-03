import discord
from discord.ext import commands
from discord import app_commands

BADGE_EMOJIS = {
    "staff": "<:staff:1399726583669067957>",
    "partner": "<:partnerServerOwner:1399727715392819370>",
    "hypesquad": "<:hypeSquad:1399728160056152115>",
    "bug_hunter": "<:bugHunter:1399727149031624744>",
    "hypesquad_bravery": "<:hypeSquadBravery:1399727787945885807>",
    "hypesquad_brilliance": "<:hypeSquadBrilliance:1399727824826404944>",
    "hypesquad_balance": "<:hypeSquadBalance:1399727765938503782>",
    "early_supporter": "<:earlySupporter:1399727741934502059>",
    "verified_bot_developer": "<:earlyVerifiedBotDeveloper:1399727863371927662>",
    "active_developer": "<:activeDeveloper:1399727916564086925>",
    # 必要に応じて他のフラグを追加
}

class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="userinfo", description="指定したユーザーの情報を表示します。")
    @app_commands.rename(user="ユーザー")
    async def userinfo(self, ctx: commands.Context, user: discord.Member = None):
        user = user or ctx.author
        if isinstance(user, discord.User) and isinstance(ctx.author, discord.Member):
            try:
                user = await ctx.guild.fetch_member(user.id)
            except discord.NotFound:
                pass

        username = f"{user.name}#{user.discriminator}" if user.bot else user.name
        embed = discord.Embed(title=f"<:info:1399034333284667422>ユーザー情報", color=discord.Color.blurple())
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name=f"<:tag:1398952153242144788>名前", value=f"{username}", inline=True)
        embed.add_field(name=f"<:tag:1398952153242144788>ユーザーID", value=str(user.id), inline=True)
        embed.add_field(name=f"<:plus:1394231723390275645>アカウント作成日", value=user.created_at.strftime("%Y/%m/%d %H:%M:%S"), inline=False)

        status = "<:offline:1399035655548721213> オフライン"  # デフォルト値（Memberでない場合）

        if isinstance(user, discord.Member):
            if user.mobile_status == discord.Status.online:
                status = "<:mobileOnline:1399864168856686692>オンライン"
            else:
                STATUS_EMOJIS = {
                    discord.Status.online: "<:online:1399861831660601534> オンライン",
                    discord.Status.idle: "<:idle:1399861830075285575> 退席中",
                    discord.Status.dnd: "<:dnd:1399861835175428197> 取り込み中",
                    discord.Status.offline: "<:offline:1399861833178812596> オフライン"
                }
                status = STATUS_EMOJIS.get(user.status, "❔ 不明")
            embed.add_field(name=f"<:ping:1399035063672504421>ステータス", value=status, inline=True)

            embed.add_field(name=f"<:guildMemberAdd:1394238624786157649>サーバー参加日", value=user.joined_at.strftime("%Y/%m/%d %H:%M:%S"), inline=False)
            roles = [role.mention for role in user.roles[1:]]  # @everyoneを除外
            embed.add_field(name=f"<:roles:1398955473797124107>ロール", value=", ".join(roles) or "なし", inline=False)

        # バッジ表示（flagsから）
        flags = user.public_flags
        badges = [emoji for flag_name, emoji in BADGE_EMOJIS.items() if getattr(flags, flag_name, False)]
        badge_str = " ".join(badges) if badges else "なし"
        embed.add_field(name="バッジ", value=badge_str, inline=False)

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Info(bot))
