import discord
from discord.ext import commands
from discord import app_commands
from datetime import timedelta, datetime
from pymongo import MongoClient
import os
from dotenv import load_dotenv

load_dotenv()

mongo_client = MongoClient(os.getenv("MONGO_URI"))

db = mongo_client["moderation"]
case_collection = db["cases"]
warns_collection = db["warnings"]

serverlog_db = mongo_client["serverlog"]
serverlog_collection = serverlog_db["channel.serverlog.channel"]

def can_moderate(actor: discord.Member, target: discord.Member, bot_member: discord.Member) -> tuple[bool, str | None]:
    # サーバーオーナーは無条件でOK
    if actor.id == actor.guild.owner_id:
        return True, None

    # 自分自身を処罰できない
    if actor.id == target.id:
        return False, "自分自身を処罰することはできません。"

    # 対象がサーバーオーナー
    if target.id == actor.guild.owner_id:
        return False, "サーバーオーナーを処罰することはできません。"

    # 実行者 vs 対象（ロール階層）
    if target.top_role >= actor.top_role:
        return False, "あなたと同等、またはそれ以上の権限を持つユーザーは処罰できません。"

    # Bot vs 対象（ロール階層）
    if target.top_role >= bot_member.top_role:
        return False, "Botの権限が不足しています（ロール階層が上です）。"

    return True, None

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def parse_duration(self, duration_str: str) -> timedelta | None:
        try:
            unit = duration_str[-1].lower()
            value = int(duration_str[:-1])

            if unit == "m":
                return timedelta(minutes=value)
            elif unit == "h":
                return timedelta(hours=value)
            elif unit == "d":
                return timedelta(days=value)
        except (ValueError, IndexError):
            return None
        return None

    async def get_log_channel(self, guild: discord.Guild):
        serverlog = serverlog_collection.find_one({"_id": guild.id})
        if not serverlog:
            return None
        log_ch_id = serverlog.get("log_channel_id")
        if not log_ch_id:
            return None
        return guild.get_channel(int(log_ch_id))

    async def send_log(self, ctx, action_type, target: discord.Member | discord.User, reason: str):
        channel = await self.get_log_channel(ctx.guild)
        if not channel:
            return

        case_data = case_collection.find_one_and_update(
            {"_id": str(ctx.guild.id)},
            {"$inc": {"case": 1}},
            upsert=True,
            return_document=True
        )
        case_number = case_data["case"]

        embed = discord.Embed(
            color=discord.Color.red() if action_type.lower() == "ban" else discord.Color.orange(),
            timestamp=datetime.now()
        )
        embed.set_author(name=f"ケース{case_number} | {action_type.upper()} | {target}", icon_url=target.display_avatar.url)
        embed.add_field(name="該当ユーザー", value=f"{target.mention}", inline=True)
        embed.add_field(name="モデレーター", value=f"{ctx.author.mention}", inline=True)
        embed.add_field(name="理由", value=reason, inline=True)
        embed.set_footer(text=f"ユーザーID:{target.id}")

        await channel.send(embed=embed)

    async def send_warn_log(self, guild: discord.Guild, moderator: discord.Member, warned_user: discord.Member, reason: str, case_id: int, warn_count: int):
        channel = await self.get_log_channel(guild)
        print(f"channelID:{channel}")
        if not channel:
            return

        embed = discord.Embed(
            color=discord.Color.yellow(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="該当ユーザー", value=warned_user.mention, inline=True)
        embed.add_field(name="モデレーター", value=moderator.mention, inline=True)
        embed.add_field(name="理由", value=reason, inline=True)
        embed.set_footer(text=f"ユーザーID:{warned_user.id}")
        embed.set_author(name=f"ケース{case_id}｜警告｜{warned_user.name}", icon_url=warned_user.display_avatar.url)
        
        try:
            await channel.send(embed=embed)
        except Exception as e:
            print(f"⚠️ メッセージ送信エラー: {e}")

    @commands.hybrid_command(name="ban", description="ユーザーをBANします。", aliases=["b"])
    @app_commands.describe(
        user="BANするユーザー",
        reason="BANの理由"
    )
    @app_commands.rename(user="ユーザー", reason="理由")
    @commands.has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, user: discord.User, *, reason: str = "理由なし"):
        """ユーザーをBANする（スラッシュ: Userオプション / プレフィックス: mention or ID対応）"""
        guild = ctx.guild
        if guild is None:
            return await ctx.reply("このコマンドはサーバー内でのみ使用できます。")

        bot_member = ctx.guild.me

        ok, error = can_moderate(ctx.author, user, bot_member)
        if not ok:
            return await ctx.reply(f"<:cross:1394240624202481705>{error}")

        # プレフィックスコマンドの場合、userが文字列(ID)かもしれない
        if isinstance(user, str):
            try:
                user = await self.bot.fetch_user(int(user))
            except Exception:
                return await ctx.reply("<:cross:1394240624202481705>ユーザーが見つかりません。")

        # すでにBAN済みか確認
        try:
            await guild.fetch_ban(user)
            return await ctx.reply(f"<:warn:1394241229176311888>{user}はすでにBANされています。")
        except discord.NotFound:
            pass

        # BAN実行
        try:
            await guild.ban(user, reason=reason)
            await ctx.reply(f"<:check:1394240622310850580>{user} をBANしました。")
            await self.send_log(ctx, "ban", user, reason)
        except discord.Forbidden:
            await ctx.reply(f"<:cross:1394240624202481705>{user.mention}をBANする権限がありません。")
        except discord.NotFound:
            await ctx.reply(f"<:cross:1394240624202481705>ユーザーが見つかりませんでした。")
        except Exception as e:
            await ctx.reply(f"<:cross:1394240624202481705>エラーが発生しました: `{e}`")


    @commands.hybrid_command(name="unban", description="ユーザーIDでBANを解除します。")
    @app_commands.describe(user_id="BANを解除するユーザーのID", reason="理由を入力")
    @app_commands.rename(user_id="ユーザーid", reason="理由")
    @commands.has_permissions(ban_members=True)
    async def unban(self, ctx, user_id: str, reason: str = "理由なし"):
        bot_member = ctx.guild.me

        try:
            user = await self.bot.fetch_user(user_id)
        except:
            return await ctx.reply("<:cross:1394240624202481705>ユーザーが見つかりません。")

        # member ではなく、取得した user を渡す
        ok, error = can_moderate(ctx.author, user, bot_member)
        if not ok:
            return await ctx.reply(f"<:cross:1394240624202481705>{error}")

        try:
            user = await self.bot.fetch_user(user_id)
            await ctx.guild.unban(user, reason=reason)
            await ctx.reply(f"<:check:1394240622310850580>{user}のBANを解除しました。")
            await self.send_log(ctx, "ban解除", user, reason)
        except discord.NotFound:
            await ctx.reply("<:warn:1394241229176311888>そのユーザーはBANされていません。")
        except discord.Forbidden:
            await ctx.reply(f"<:cross:1394240624202481705>{user}のBANを解除するする権限がありません。")
        except Exception as e:
            await ctx.reply(f"<:cross:1394240624202481705>エラーが発生しました: `{e}`")

    @commands.hybrid_command(name="kick", description="ユーザーをキックします。", aliases=["k"])
    @app_commands.describe(member="対象ユーザー", reason="理由を入力")
    @app_commands.rename(member="ユーザー", reason="理由")
    @commands.has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "理由なし"):
        bot_member = ctx.guild.me

        ok, error = can_moderate(ctx.author, member, bot_member)
        if not ok:
            return await ctx.reply(f"<:cross:1394240624202481705>{error}")

        try:
            await member.kick(reason=reason)
            await ctx.reply(f"<:check:1394240622310850580>{member.mention}をキックしました。")
            await self.send_log(ctx, "キック", member, reason)
        except discord.Forbidden:
            await ctx.reply(f"<:cross:1394240624202481705>{member.mention}をキックする権限がありません。")
        except Exception as e:
            await ctx.reply(f"<:cross:1394240624202481705>エラーが発生しました: `{e}`")

    @commands.hybrid_command(name="timeout", description="ユーザーをタイムアウトします。", aliases=["to"])
    @app_commands.describe(member="対象ユーザー", duration="期間", reason="理由を入力")
    @app_commands.rename(member="ユーザー", duration="期間", reason="理由")
    @commands.has_permissions(moderate_members=True)
    async def timeout(self, ctx: commands.Context, member: discord.Member, duration: str, *, reason: str = "理由なし"):
        bot_member = ctx.guild.me

        ok, error = can_moderate(ctx.author, member, bot_member)
        if not ok:
            return await ctx.reply(f"<:cross:1394240624202481705>{error}")

        time_delta = self.parse_duration(duration)
        if not time_delta:
            await ctx.reply(f"<:cross:1394240624202481705>時間の形式が無効です。例: `1m`, `2h`, `3d`")
            return

        try:
            await member.timeout(time_delta, reason=reason)
            await ctx.reply(f"<:check:1394240622310850580>{member.mention}をタイムアウトしました。")
            await self.send_log(ctx, "タイムアウト", member, reason)
        except discord.Forbidden:
            await ctx.reply(f"<:cross:1394240624202481705>{member.mention}をタイムアウトする権限がありません。")
        except Exception as e:
            await ctx.reply(f"<:cross:1394240624202481705>エラーが発生しました: `{e}`")

    @commands.hybrid_command(name="untimeout", description="ユーザーのタイムアウトを解除します。", aliases=["unto"])
    @app_commands.describe(member="該当ユーザー", reason="理由を入力")
    @app_commands.rename(member="ユーザー", reason="理由")
    @commands.has_permissions(moderate_members=True)
    async def untimeout(self, ctx: commands.Context, member: discord.Member, *, reason: str = "理由なし"):
        bot_member = ctx.guild.me

        ok, error = can_moderate(ctx.author, member, bot_member)
        if not ok:
            return await ctx.reply(f"<:cross:1394240624202481705>{error}")

        try:
            await member.timeout(None, reason=reason)
            await ctx.reply(f"<:check:1394240622310850580>{member.mention}のタイムアウトを解除しました。")
            await self.send_log(ctx, "タイムアウト解除", member, reason)
        except discord.Forbidden:
            await ctx.reply(f"<:cross:1394240624202481705>{member.mention}のタイムアウトを解除する権限がありません。")
        except Exception as e:
            await ctx.reply(f"<:cross:1394240624202481705>エラーが発生しました: `{e}`")

    @commands.hybrid_command(name="warn", description="ユーザーに警告を与えます。")
    @app_commands.describe(member="該当ユーザー", reason="理由を入力")
    @app_commands.rename(member="ユーザー", reason="理由")
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "理由なし"):
        bot_member = ctx.guild.me

        ok, error = can_moderate(ctx.author, member, bot_member)
        if not ok:
            return await ctx.reply(f"<:cross:1394240624202481705>{error}")

        warns_collection.insert_one({
            "user_id": member.id,
            "guild_id": ctx.guild.id,
            "moderator_id": ctx.author.id,
            "reason": reason,
            "timestamp": datetime.now()
        })

        # DMで通知
        embed = discord.Embed(
            title=f"<:warning2:1402472011393142934>あなたは{ctx.guild.name}の管理者により警告されました。",
            description=f"**理由**: {reason}",
            color=discord.Color.red()
        )
        try:
            await member.send(embed=embed)
        except discord.Forbidden:
            pass

        await ctx.reply(f"<:check:1394240622310850580>{member.mention} に警告を与えました。")

        warn_count = warns_collection.count_documents({"user_id": member.id, "guild_id": ctx.guild.id})

        # ケース番号の取得・更新
        case_data = case_collection.find_one_and_update(
            {"_id": str(ctx.guild.id)},
            {"$inc": {"case": 1}},
            upsert=True,
            return_document=True
        )
        case_number = case_data["case"]

        # ログ送信
        await self.send_warn_log(ctx.guild, ctx.author, member, reason, case_number, warn_count)

    @commands.hybrid_command(name="warnings", description="警告履歴を確認します。")
    @app_commands.describe(member="確認するユーザー")
    @app_commands.rename(member="ユーザー")
    @commands.has_permissions(moderate_members=True)
    async def warnings(self, ctx: commands.Context, member: discord.Member):
        warns = list(warns_collection.find({"user_id": member.id, "guild_id": ctx.guild.id}))
        if not warns:
            await ctx.reply(f"{member.mention}の警告履歴はありません。")
            return

        embed = discord.Embed(
            title=f"{member.display_name} の警告履歴",
            color=discord.Color.orange()
        )

        for i, w in enumerate(warns[-5:], 1):
            mod = ctx.guild.get_member(w["moderator_id"])
            mod_name = mod.display_name if mod else "不明"
            date_str = w["timestamp"].strftime("%Y/%m/%d %H:%M")
            embed.add_field(
                name=f"警告 {i}（{date_str}）",
                value=f"モデレーター: {mod_name}\n理由: {w['reason']}",
                inline=False
            )

        await ctx.reply(embed=embed)

    @commands.hybrid_command(name="delwarn", description="特定の警告を削除します。", aliases=["dwarn"])
    @app_commands.describe(member="対象のユーザー", index="削除する警告の番号（1から）")
    @app_commands.rename(member="ユーザー", index="番号")
    @commands.has_permissions(moderate_members=True)
    async def delwarn(self, ctx: commands.Context, member: discord.Member, index: int):
        warns = list(warns_collection.find({"user_id": member.id, "guild_id": ctx.guild.id}))

        if not warns:
            await ctx.reply(f"<:warn:1394241229176311888>{member.mention}の警告はありません。")
            return

        if index < 1 or index > len(warns):
            await ctx.reply(f"<:cross:1394240624202481705>指定された番号が無効です。")
            return

        warn_to_delete = warns[index - 1]
        warns_collection.delete_one({"_id": warn_to_delete["_id"]})

        await ctx.reply(f"<:check:1394240622310850580>{member.mention}の警告 #{index}を削除しました。")

    @commands.hybrid_command(name="clearwarn", description="すべての警告を削除します。", aliases=["cwarn"])
    @app_commands.describe(member="対象のユーザー")
    @app_commands.rename(member="ユーザー")
    @commands.has_permissions(moderate_members=True)
    async def clearwarn(self, ctx: commands.Context, member: discord.Member):
        result = warns_collection.delete_many({"user_id": member.id, "guild_id": ctx.guild.id})

        if result.deleted_count == 0:
            await ctx.reply(f"<:warn:1394241229176311888>{member.mention}の警告はありません。")
        else:
            await ctx.reply(f"<:check:1394240622310850580>{member.mention}の警告を全て削除しました。")

    @commands.hybrid_command(name="softban", description="ユーザーを一度BANしてすぐ解除します。（メッセージ削除）", aliases=["sban", "sb"])
    @app_commands.describe(member="対象のユーザー", reason="理由を入力")
    @app_commands.rename(member="ユーザー", reason="理由")
    @commands.has_permissions(ban_members=True)
    async def softban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "理由なし"):
        bot_member = ctx.guild.me

        ok, error = can_moderate(ctx.author, member, bot_member)
        if not ok:
            return await ctx.reply(f"<:cross:1394240624202481705>{error}")

        try:
            await member.ban(reason=reason, delete_message_days=1)
            await member.unban(reason="ソフトBAN解除")
            await ctx.reply(f"<:check:1394240622310850580> {member.mention} をソフトBANしました。")
            await self.send_log(ctx, "ソフトBAN", member, reason)
        except discord.Forbidden:
            await ctx.reply(f"<:cross:1394240624202481705>{member.mention}をBANする権限がありません。")
        except Exception as e:
            await ctx.reply(f"<:cross:1394240624202481705>エラーが発生しました: `{e}`")

    @commands.hybrid_command(name="massban", description="複数のユーザーをIDでBANします。（コンマ区切り）", aliases=["mban", "mb"])
    @app_commands.describe(ids="対象のユーザーID(コンマ区切り)", reason="理由を入力")
    @app_commands.rename(ids="ユーザーid", reason="理由")
    @commands.has_permissions(ban_members=True)
    async def massban(self, ctx: commands.Context, ids: str, *, reason: str = "理由なし"):
        bot_member = ctx.guild.me

        ok, error = can_moderate(ctx.author, user, bot_member)
        if not ok:
            return await ctx.reply(f"<:cross:1394240624202481705>{error}")
            
        user_ids = [uid.strip() for uid in ids.split(",")]
        success = []
        failed = []

        for uid in user_ids:
            try:
                user = await self.bot.fetch_user(int(uid))
                await ctx.guild.ban(user, reason=reason)
                success.append(uid)
                await self.send_log(ctx, "BAN", user, reason)
            except Exception as e:
                failed.append((uid, str(e)))

        msg = ""
        if success:
            msg += f"<:check:1394240622310850580>成功: `{', '.join(success)}`\n"
        if failed:
            msg += f"<:cross:1394240624202481705>失敗:\n"
            for f in failed:
                msg += f"- `{f[0]}`: {f[1]}\n"

        await ctx.reply(msg)


    @ban.error
    @unban.error
    @kick.error
    @timeout.error
    @untimeout.error
    @softban.error
    async def moderation_error(self, ctx: commands.Context, error):
        cmd_name = ctx.command.name if ctx.command else None

        if isinstance(error, commands.MissingPermissions):
            permission_message = {
                "ban": f"<:cross:1394240624202481705>このコマンドを使うにはメンバーのBAN権限が必要です。",
                "softban": f"<:cross:1394240624202481705>このコマンドを使うにはメンバーのBAN権限が必要です。",
                "massban": f"<:cross:1394240624202481705>このコマンドを使うにはメンバーのBAN権限が必要です。",
                "unban": f"<:cross:1394240624202481705>このコマンドを使うにはメンバーのBAN権限が必要です。",
                "kick": f"<:cross:1394240624202481705>このコマンドを使うにはメンバーのキック権限が必要です。",
                "timeout": f"<:cross:1394240624202481705>このコマンドを使うにはメンバーの管理権限が必要です。",
                "untimeout": f"<:cross:1394240624202481705>このコマンドを使うにはメンバーの管理権限が必要です。",
                "warn": f"<:cross:1394240624202481705>このコマンドを使うにはメンバーの管理権限が必要です。",
                "warnings": f"<:cross:1394240624202481705>このコマンドを使うにはメンバーの管理権限が必要です。",
                "delwarn": f"<:cross:1394240624202481705>このコマンドを使うにはメンバーの管理権限が必要です。",
                "clearwarn": f"<:cross:1394240624202481705>このコマンドを使うにはメンバーの管理権限が必要です。"
            }
            await ctx.reply(permission_message.get(cmd_name, "このコマンドを使うには適切な権限が必要です。"))
            return
        
        elif isinstance(error, commands.MissingRequiredArgument):
            usage_message = {
                "ban": "使用方法: `zd!ban @ユーザー (理由)`",
                "softban": "使用方法: `zd!softban @ユーザー (理由)`",
                "massban": "使用方法: `zd!massban ユーザーID(コンマ区切り) (理由)`",
                "unban": "使用方法: `zd!unban ユーザーID (理由)`",
                "kick": "使用方法: `zd!kick @ユーザー (理由)`",
                "timeout": "使用方法: `zd!timeout @ユーザー 1m (理由)`\n時間の単位: `m`=分, `h`=時間, `d`=日",
                "untimeout": "使用方法: `zd!untimeout @ユーザー (理由)`",
                "warn": "使用方法: `zd!warn @ユーザー (理由)`",
                "warnings": "使用方法: `zd!warnings @ユーザー`",
                "delwarn": "使用方法: `zd!delwarn @ユーザー 警告番号`",
                "clearwarn": "使用方法: `zd!clearwarn @ユーザー`"
            }
            await ctx.reply(usage_message.get(cmd_name, "引数が不足しています。"))
            return

        elif isinstance(error, commands.BadArgument):
            await ctx.reply(f"<:warn:1394241229176311888>ユーザーが見つかりません。メンションを使ってください。")
            return

        else:
            await ctx.reply(f"<:warn:1394241229176311888>エラーが発生しました: {error}")


async def setup(bot):
    await bot.add_cog(Moderation(bot))
