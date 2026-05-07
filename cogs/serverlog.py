import discord
from discord.ext import commands
from discord import app_commands
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
import math

load_dotenv()

mongo_client = AsyncIOMotorClient(os.getenv("MONGO_URI"))
db = mongo_client["serverlog"]["channel"]
log_collection = db["serverlog"]["channel"]

db1 = mongo_client["automod"]
exception_collection = db1["exceptions"]

perm_name_map = {
    "view_channel": "チャンネルを見る",
    "read_messages": "チャンネルを見る",
    "manage_channels": "チャンネルの管理",
    "manage_roles": "ロールの管理",
    "create_expressions": "エクスプレッションを作成",
    "manage_emojis_and_stickers": "絵文字の管理",
    "manage_permissions": "権限の管理",
    "view_audit_log": "監査ログを表示",
    "manage_webhooks": "ウェブフックの管理",
    "manage_guild": "サーバー管理",
    "create_instant_invite": "招待を作成",
    "change_nickname": "ニックネームの変更",
    "manage_nicknames": "ニックネームの管理",
    "kick_members": "メンバーのキック、承認、拒否",
    "ban_members": "メンバーをBAN",
    "moderate_members": "メンバーをタイムアウト",
    "send_messages": "メッセージの送信と投稿の作成",
    "send_messages_in_threads": "スレッドと投稿でメッセージを送信",
    "create_public_threads": "公開スレッドの作成",
    "create_private_threads": "プライベートスレッドの作成",
    "embed_links": "埋め込みリンク",
    "attach_files": "ファイルを添付",
    "add_reactions": "リアクションの追加",
    "use_external_emojis": "外部の絵文字を使用する",
    "external_emojis": "外部の絵文字を使用する",
    "use_external_stickers": "外部のスタンプを使用する",
    "external_stickers": "外部のスタンプを使用する",
    "mention_everyone": "@everyone、@here、全てのロールにメンション",
    "manage_messages": "メッセージの管理",
    "pin_messages": "メッセージをピン留め",
    "manage_threads": "スレッドと投稿の管理",
    "read_message_history": "メッセージ履歴を読む",
    "send_tts_messages": "テキスト読み上げメッセージを送信する",
    "send_voice_messages": "ボイスメッセージを送信",
    "send_polls": "投票の作成",
    "create_polls": "投票の作成",
    "connect": "接続",
    "speak": "発言",
    "stream": "WEBカメラ",
    "use_soundboard": "サウンドボードを使用",
    "use_external_sounds": "外部のサウンドの使用",
    "use_vad": "音声検出を使用",
    "use_voice_activation": "音声検出を使用",
    "priority_speaker": "優先スピーカー",
    "mute_members": "メンバーをミュート",
    "deafen_members": "メンバーのスピーカーをミュート",
    "move_members": "メンバーを移動",
    "set_voice_channel_status": "ボイスチャンネルステータスを設定",
    "use_application_commands": "アプリコマンドを使う",
    "use_embedded_activities": "ユーザーアクティビティ",
    "use_external_apps": "外部のアプリを使用",
    "create_events": "イベントを作成",
    "manage_events": "イベントの管理",
    "request_to_speak": "スピーカー参加をリクエスト",
    "administrator": "管理者",
}

skip_perms = {
    "read_messages",
    "create_polls",
    "external_emojis",
    "external_stickers",
    "manage_permissions",
    "manage_expressions",
}

def get_permission_changes(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel) -> str:
    changes = []

    all_targets = set(before.overwrites.keys()).union(set(after.overwrites.keys()))

    for target in all_targets:
        before_overwrite = before.overwrites.get(target)
        after_overwrite = after.overwrites.get(target)

        if before_overwrite != after_overwrite:
            target_name = target.name if hasattr(target, "name") else str(target)

            perms_changed = []
            for perm_name in discord.Permissions.VALID_FLAGS:
                if perm_name == "read_messages":
                    continue

                b = getattr(before_overwrite, perm_name, None) if before_overwrite else None
                a = getattr(after_overwrite, perm_name, None) if after_overwrite else None

                if b != a:
                    symbol = ""
                    if a is True:
                        symbol = "<:check:1394240622310850580>"
                    elif a is False:
                        symbol = "<:cross:1394240624202481705>"
                    elif a is None:
                        symbol = "<:neutral:1398885734676562022>"

                    jp_name = perm_name_map.get(perm_name, perm_name.replace("_", " "))
                    perms_changed.append(f"{symbol}{jp_name}")

            if perms_changed:
                formatted = "\n".join(perms_changed)
                changes.append(f"- **{target_name}**\n{formatted}")

    return "\n\n".join(changes) if changes else ""



def get_channel_type_name(channel: discord.abc.GuildChannel) -> str:
    if isinstance(channel, discord.TextChannel):
        return "テキストチャンネル"
    elif isinstance(channel, discord.VoiceChannel):
        return "ボイスチャンネル"
    elif isinstance(channel, discord.CategoryChannel):
        return "カテゴリー"
    elif isinstance(channel, discord.StageChannel):
        return "ステージ"
    elif isinstance(channel, discord.ForumChannel):
        return "フォーラムチャンネル"
    elif isinstance(channel, discord.NewsChannel):
        return "アナウンスチャンネル"
    else:
        return "不明なチャンネル種別"

async def is_exempted_from_log(guild_id: int, channel_id: int, user_id: int) -> bool:
    """ログ記録の例外を確認"""
    # チャンネルが例外対象か確認
    for key, target_type, target_id in [
        (f"{guild_id}-channel-{channel_id}", "channel", channel_id),
        (f"{guild_id}-user-{user_id}", "user", user_id)
    ]:
        data = await exception_collection.find_one({"_id": key})
        if data and data.get("send_log"):
            return True
    return False

class ServerLogCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log_channels = {}
        # main.pyで定義したMONGO_URIを使ってここでコレクションを定義するか、
        # あるいはbotオブジェクトに持たせたdbを利用します。
        self.db_client = motor.motor_asyncio.AsyncIOMotorClient(os.environ.get('MONGO_URI'))
        self.collection = self.db_client['your_db_name']['server_logs']

    async def cog_load(self):
        """Cogロード時にMongoDBからキャッシュを読み込む"""
        print(f"[{self.__class__.__name__}] データの読み込みを開始します...")
        try:
            # self.collection (上で定義したもの) を使用する
            cursor = self.collection.find().max_time_ms(5000)
            async for doc in cursor:
                # ドキュメントの構造に合わせて調整 (例: _id が文字列か数値か)
                self.log_channels[str(doc["_id"])] = doc["log_channel_id"]
            
            print(f"[{self.__class__.__name__}] {len(self.log_channels)}件のデータをロードしました。")
        except Exception as e:
            print(f"[{self.__class__.__name__}] データのロード中にエラーが発生しました: {e}")
            self.log_channels = {}

    async def get_log_channel(self, guild: discord.Guild):
        # キャッシュからチャンネルIDを取得
        log_channel_id = self.log_channels.get(str(guild.id))
        if log_channel_id:
            return guild.get_channel(log_channel_id)
        return None

    async def send_log(self, guild: discord.Guild, embed: discord.Embed):
        log_channel = await self.get_log_channel(guild)
        if log_channel:
            try:
                await log_channel.send(embed=embed)
            except Exception as e:
                print(f"ログ送信失敗: {e}")

    @commands.hybrid_group(name="logging", description="ログの記録設定")
    async def logging(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.reply("使用方法: `r!logging enable #チャンネル` または `r!logging disable`")

    @logging.command(name="enable", description="ログの記録を有効にします。")
    @app_commands.describe(channel="記録先を選択")
    @app_commands.rename(channel="チャンネル")
    async def logging_enable(self, ctx: commands.Context, channel: discord.TextChannel):
        if not ctx.author.guild_permissions.administrator:
            await ctx.reply("<:cross:1394240624202481705> このコマンドを実行するには管理者権限が必要です。", ephemeral=True)
            return
        
        await log_collection.update_one(
            {"_id": ctx.guild.id},
            {"$set": {"log_channel_id": channel.id}},
            upsert=True
        )
        self.log_channels[str(ctx.guild.id)] = channel.id
        await ctx.reply(f"<:check:1394240622310850580> ログの記録先を {channel.mention} に設定しました。", mention_author=False)

    @logging.command(name="disable", description="ログの記録を無効にします。")
    async def logging_disable(self, ctx: commands.Context):
        if not ctx.author.guild_permissions.administrator:
            await ctx.reply("<:cross:1394240624202481705> このコマンドを実行するには管理者権限が必要です。", ephemeral=True)
            return
        
        await log_collection.delete_one({"_id": ctx.guild.id})
        self.log_channels.pop(str(ctx.guild.id), None)
        await ctx.reply("<:check:1394240622310850580> ログの記録を無効にしました。", mention_author=False)



    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if await is_exempted_from_log(member.guild.id, None, member.id):
            return
        now = discord.utils.utcnow()
        created_at_unix = int(member.created_at.timestamp())
        embed = discord.Embed(
            description=f"<:guildMemberAdd:1394238624786157649><@{member.id}>が参加しました。\nアカウント作成日:<t:{created_at_unix}:D>(<t:{created_at_unix}:R>)",
            color=discord.Color.green(),
            timestamp=now
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.set_footer(text=f"ユーザーID:{member.id}")
        embed.set_thumbnail(url=member.display_avatar.url)
        try:
            await self.send_log(member.guild, embed)
        except Exception as e:
            print(f"⚠️ メッセージ送信エラー: {e}")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if await is_exempted_from_log(member.guild.id, None, member.id):
            return
        now = discord.utils.utcnow()
        embed = discord.Embed(
            description=f"<:guildMemberRemove:1394238635653464104><@{member.id}>が退出しました。",
            color=discord.Color.red(),
            timestamp=now
        )
        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.set_footer(text=f"ユーザーID:{member.id}")
        embed.set_thumbnail(url=member.display_avatar.url)
        try:
            await self.send_log(member.guild, embed)
        except Exception as e:
            print(f"⚠️ メッセージ送信エラー: {e}")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None:
            return

        log_channel = await self.get_log_channel(message.guild)
        if not log_channel:
            return

        if await is_exempted_from_log(message.guild.id, message.channel.id, message.author.id):
            return

        now = discord.utils.utcnow()

        embed = discord.Embed(
            description=f"**<:messageDelete:1394236737743753216>{message.channel.mention}で送信された{message.author.mention}のメッセージが削除されました。**",
            color=discord.Color.red(),
            timestamp=now
        )

        if message.attachments:
            files = "\n".join(f"[{a.filename}]({a.url})" for a in message.attachments)
            embed.add_field(name="添付ファイル", value=files, inline=False)
        else:
            embed.add_field(name="添付ファイル", value="なし", inline=False)

        content = message.content or "（なし）"
        embed.add_field(name="内容", value=f"```{content}```", inline=False)

        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.set_footer(text=f"ユーザーID:{message.author.id}")
        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"⚠️ メッセージ送信エラー: {e}")

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.guild is None or before.content == after.content:
            return

        log_channel = await self.get_log_channel(before.guild)
        if not log_channel:
            return

        if await is_exempted_from_log(before.guild.id, before.channel.id, before.author.id):
            return

        now = discord.utils.utcnow()

        embed = discord.Embed(
            description=f"**<:messageEdit:1394236727412916234>{before.author.mention}が{before.channel.mention}に送信した[メッセージ](https://discord.com/channels/{before.guild.id}/{before.channel.id}/{before.id})を編集しました。**",
            color=discord.Color.orange(),
            timestamp=now
        )

        embed.add_field(name="編集前", value=f"```{before.content or '（なし）'}```", inline=False)
        embed.add_field(name="編集後", value=f"```{after.content or '（なし）'}```", inline=False)

        if after.attachments:
            files = "\n".join(f"[{a.filename}]({a.url})" for a in after.attachments)
            embed.add_field(name="添付ファイル（編集後）", value=files, inline=False)

        embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
        embed.set_footer(text=f"ユーザーID:{before.author.id}")
        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"⚠️ メッセージ送信エラー: {e}")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if await is_exempted_from_log(member.guild.id, after.channel.id if after.channel else before.channel.id, member.id):
            return
        now = discord.utils.utcnow()
        if before.channel is None and after.channel is not None:
            channel = after.channel
            embed = discord.Embed(
                description=(
                    f"**<:vcJoin:1394236800238751825><@{member.id}> がボイスチャンネル<#{channel.id}>に参加しました。**\n"
                    f"人数制限:{channel.user_limit if channel.user_limit else 0}人"
                ),
                color=discord.Color.teal(),
                timestamp=now
            )
        elif before.channel is not None and after.channel is None:
            channel = before.channel
            embed = discord.Embed(
                description=(
                    f"**<:vcLeave:1394236824745934879><@{member.id}> がボイスチャンネル<#{channel.id}>から退出しました。**\n"
                    f"人数制限:{channel.user_limit if channel.user_limit else 0}人"
                ),
                color=discord.Color.dark_teal(),
                timestamp=now
            )
        elif before.channel != after.channel:
            before.channel = before.channel
            after.channel = after.channel
            embed = discord.Embed(
                description=(
                    f"**<:vcSwitch:1394236814054785054><@{member.id}> がボイスチャンネル<#{before.channel.id}>から<#{after.channel.id}>に移動しました。**\n"
                    f"<#{before.channel.id}>の人数制限:{before.channel.user_limit if before.channel.user_limit else 0}人\n"
                    f"<#{after.channel.id}>の人数制限:{after.channel.user_limit if after.channel.user_limit else 0}人"
                ),
                color=discord.Color.dark_teal(),
                timestamp=now
            )
        else:
            return

        embed.set_author(name=str(member), icon_url=member.display_avatar.url)
        embed.set_footer(text=f"ユーザーID:{member.id}")
        try:
            await self.send_log(member.guild, embed)
        except Exception as e:
            print(f"⚠️ メッセージ送信エラー: {e}")

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        if await is_exempted_from_log(guild.id, None, user.id):
            return
        log_channel = await self.get_log_channel(guild)
        if not log_channel:
            return

        reason = "なし"
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                if entry.target.id == user.id:
                    if entry.reason:
                        reason = entry.reason
                    break
        except discord.Forbidden:
            reason = "<:warn:1394241229176311888>理由を取得できません。"

        now = discord.utils.utcnow()

        embed = discord.Embed(
            description=f"**<:guildBanAdd:1394238714213040139><@{user.id}> がBANされました。**\n理由:**{reason}**",
            color=discord.Color.red(),
            timestamp=now
        )
        embed.set_footer(text=f"ユーザーID:{user.id}")
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.set_thumbnail(url=user.display_avatar.url)
        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"⚠️ メッセージ送信エラー: {e}")

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        if await is_exempted_from_log(guild.id, None, user.id):
            return
        log_channel = await self.get_log_channel(guild)
        if not log_channel:
            return
        
        now = discord.utils.utcnow()

        embed = discord.Embed(
            description=f"**<:guildBanRemove:1394238720512622592><@{user.id}> のBANが解除されました。**",
            color=discord.Color.orange(),
            timestamp=now
        )
        embed.set_footer(text=f"ユーザーID:{user.id}")
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.set_thumbnail(url=user.display_avatar.url)
        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"⚠️ メッセージ送信エラー: {e}")

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        if await is_exempted_from_log(channel.guild.id, channel.id, self.bot.user.id):
            return
        log_channel = await self.get_log_channel(channel.guild)
        if not log_channel:
            return

        channel_type = get_channel_type_name(channel)
        now = discord.utils.utcnow()

        embed = discord.Embed(
            description=f"**<:channelCreate:1394236765476229160>{channel_type}<#{channel.id}>が作成されました。**",
            color=discord.Color.green(),
            timestamp=now
        )

        if hasattr(channel, "nsfw"):
            embed.add_field(name="NSFW", value="はい" if channel.nsfw else "いいえ", inline=False)

        embed.set_footer(text=f"チャンネルID:{channel.id}")
        embed.set_author(name=channel.guild.name, icon_url=channel.guild.icon.url if channel.guild.icon else None)

        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"メッセージ送信エラー: {e}")
    
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        if await is_exempted_from_log(channel.guild.id, channel.id, self.bot.user.id):
            return
        log_channel = await self.get_log_channel(channel.guild)
        if not log_channel:
            return

        channel_type = get_channel_type_name(channel)
        now = discord.utils.utcnow()
        embed = discord.Embed(
            description=f"**<:channelDelete:1394236785198104588>{channel_type}「{channel.name}」が削除されました。**",
            color=discord.Color.red(),
            timestamp=now
        )

        if hasattr(channel, "nsfw"):
            embed.add_field(name="NSFW", value="はい" if channel.nsfw else "いいえ", inline=False)

        embed.set_footer(text=f"チャンネルID:{channel.id}")
        embed.set_author(name=channel.guild.name, icon_url=channel.guild.icon.url if channel.guild.icon else None)

        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"メッセージ送信エラー: {e}")

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        if await is_exempted_from_log(after.guild.id, after.id, self.bot.user.id):
            return
        log_channel = await self.get_log_channel(after.guild)
        if not log_channel:
            return

        changes = []

        if before.name != after.name:
            changes.append(f"**<:tag:1398952153242144788>名前**\n`{before.name}` → `{after.name}`")

        if hasattr(before, "topic") and hasattr(after, "topic") and before.topic != after.topic:
            changes.append(f"**<:message:1398953333175353395>トピック**\n`{before.topic or 'なし'}` → `{after.topic or 'なし'}`")

        if hasattr(before, "nsfw") and hasattr(after, "nsfw") and before.nsfw != after.nsfw:
            changes.append(f"**<:nsfw:1398952436546273361>NSFW**\n`{'はい' if before.nsfw else 'いいえ'}` → `{'はい' if after.nsfw else 'いいえ'}`")

        if hasattr(before, "slowmode_delay") and hasattr(after, "slowmode_delay") and before.slowmode_delay != after.slowmode_delay:
            changes.append(f"**<:timeoutRemove:1394658825491058768>低速モード**\n`{before.slowmode_delay}秒` → `{after.slowmode_delay}秒`")

        perm_changes = get_permission_changes(before, after)
        if perm_changes:
            changes.append(f"**<:key:1398953112575938652>権限**\n{perm_changes}")

        if not changes:
            return

        channel_type = get_channel_type_name(after)
        now = discord.utils.utcnow()

        embed = discord.Embed(
            description=(
                f"**<:channelUpdate:1394236775588954264>{channel_type}<#{after.id}>が更新されました。**\n\n"
                + "\n\n".join(changes)
            ),
            color=discord.Color.orange(),
            timestamp=now
        )

        embed.set_footer(text=f"チャンネルID:{after.id}")
        embed.set_author(name=after.guild.name, icon_url=after.guild.icon.url if after.guild.icon else None)

        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"⚠️ メッセージ送信エラー: {e}")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        guild_id = str(after.guild.id)
        log_channel = await self.get_log_channel(after.guild)
        if not log_channel:
            return

        # タイムアウトが設定された場合
        if after.timed_out_until:
            now = discord.utils.utcnow()
            until = after.timed_out_until
            delta = until - now
            seconds = (after.timed_out_until - now).total_seconds() + 1

            if delta.total_seconds() <= 0:
                return  # すでに切れている場合はスキップ

            # 時間の長さを整形（分・時間・日）
            if seconds < 60:
                duration_str = f"{int(seconds)}秒間"
            elif seconds < 3600:
                duration_str = f"{math.floor(seconds / 60)}分間"
            elif seconds < 86400:
                duration_str = f"{math.floor(seconds / 3600)}時間"
            else:
                duration_str = f"{math.floor(seconds / 86400)}日間"

            embed = discord.Embed(
                description=f"**<:timeoutAdd:1394658819556245667><@{after.id}>は{duration_str}タイムアウトされました。**",
                color=discord.Color.orange(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"ユーザーID: {after.id}")
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            try:
                await log_channel.send(embed=embed)
            except Exception as e:
                print(f"⚠️ メッセージ送信エラー: {e}")

        # タイムアウト解除された場合
        elif before.timed_out_until and not after.timed_out_until:
            embed = discord.Embed(
                description=f"**<:timeoutRemove:1394658825491058768><@{after.id}> のタイムアウトが解除されました。**",
                color=discord.Color.green(),
                timestamp=discord.utils.utcnow()
            )
            embed.set_footer(text=f"ユーザーID: {after.id}")
            embed.set_author(name=str(after), icon_url=after.display_avatar.url)
            try:
                await log_channel.send(embed=embed)
            except Exception as e:
                print(f"⚠️ メッセージ送信エラー: {e}")


        nickname_changed = before.nick != after.nick
        role_changes = []

        # ロールの変更検出
        before_roles = set(before.roles)
        after_roles = set(after.roles)

        added_roles = after_roles - before_roles
        removed_roles = before_roles - after_roles

        for role in added_roles:
            role_changes.append(f"<:plus:1394231723390275645><@&{role.id}>")
        for role in removed_roles:
            role_changes.append(f"<:minus:1394231720995197158><@&{role.id}>")

        if not nickname_changed and not role_changes:
            return  # 変更がなければ送信しない

        now = discord.utils.utcnow()

        embed = discord.Embed(
            description=f"**<:guildMemberUpdate:1398945288131055636><@{after.id}>が更新されました。**",
            color=discord.Color.blurple(),
            timestamp=now
        )
        embed.set_author(name=str(after), icon_url=after.display_avatar.url)
        embed.set_footer(text=f"ユーザーID: {after.id}")

        # ニックネーム変更がある場合、フィールドに追加
        if nickname_changed:
            embed.add_field(
                name=f"<:tag:1398952153242144788>ニックネーム",
                value=f"`{before.nick or before.name}` → `{after.nick or after.name}`",
                inline=False
            )

        # ロール変更がある場合、フィールドに追加
        if role_changes:
            embed.add_field(
                name=f"<:roles:1398955473797124107>ロール",
                value="\n".join(role_changes),
                inline=False
            )

        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"⚠️ メッセージ送信エラー: {e}")


    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        log_channel = await self.get_log_channel(role.guild)
        if not log_channel:
            return

        now = discord.utils.utcnow()

        embed = discord.Embed(
            description=f"**<:roleCreate:1398955487139205121>ロール<@&{role.id}>が作成されました。**",
            color=discord.Color.green(),
            timestamp=now
        )
        embed.set_footer(text=f"ロールID: {role.id}")
        embed.set_author(name=role.guild.name, icon_url=role.guild.icon.url if role.guild.icon else None)

        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"⚠️ メッセージ送信エラー: {e}")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        log_channel = await self.get_log_channel(role.guild)
        if not log_channel:
            return

        now = discord.utils.utcnow()
        embed = discord.Embed(
            description=f"**<:roleDelete:1398955501299044466>ロール「{role.name}」が削除されました。**",
            color=discord.Color.red(),
            timestamp=now
        )
        embed.set_footer(text=f"ロールID: {role.id}")
        embed.set_author(name=role.guild.name, icon_url=role.guild.icon.url if role.guild.icon else None)

        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"⚠️ メッセージ送信エラー: {e}")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        log_channel = await self.get_log_channel(after.guild)
        if not log_channel:
            return

        changes = []
        name_change = None
        color_change = None
        perm_changes = []

        # --- 名前変更 ---
        if before.name != after.name:
            name_change = f"`{before.name}` → `{after.name}`"

        # --- 色変更 ---
        if before.color != after.color:
            color_change = f"\n`{before.color}` → `{after.color}`"

        # --- 権限変更 ---
        if before.permissions != after.permissions:
            before_perms = [name for name, val in before.permissions if val]
            after_perms = [name for name, val in after.permissions if val]
            removed = set(before_perms) - set(after_perms)
            added = set(after_perms) - set(before_perms)

            for perm in added:
                if perm in skip_perms:
                    continue
                jp_name = perm_name_map.get(perm, perm.replace("_", " "))
                perm_changes.append(f"<:check:1394240622310850580>{jp_name}")

            for perm in removed:
                if perm in skip_perms:
                    continue
                jp_name = perm_name_map.get(perm, perm.replace("_", " "))
                perm_changes.append(f"<:cross:1394240624202481705>{jp_name}")

        if not any([name_change, color_change, perm_changes]):
            return

        now = discord.utils.utcnow()
        embed = discord.Embed(
            description=f"**<:roleUpdate:1398955494831554680>ロール<@&{after.id}>が編集されました。**",
            color=discord.Color.orange(),
            timestamp=now
        )
        embed.set_footer(text=f"ロールID: {after.id}")
        embed.set_author(name=after.guild.name, icon_url=after.guild.icon.url if after.guild.icon else None)

        # --- 個別フィールド ---
        if name_change:
            embed.add_field(name="<:tag:1398952153242144788>名前", value=name_change, inline=False)
        if color_change:
            embed.add_field(name="<:color:1398959881855307877>色", value=color_change, inline=False)

        # --- 権限フィールド ---
        if perm_changes:
            lines = perm_changes
            chunk = ""
            chunks = []
            for line in lines:
                if len(chunk) + len(line) + 1 > 1024:
                    chunks.append(chunk.strip())
                    chunk = ""
                chunk += line + "\n"
            if chunk.strip():
                chunks.append(chunk.strip())

            for i, c in enumerate(chunks):
                field_name = "<:key:1398953112575938652>権限" if i == 0 else f"<:key:1398953112575938652>権限（続き{i}）"
                embed.add_field(name=field_name, value=c, inline=False)
    
        try:
            await log_channel.send(embed=embed)
        except Exception as e:
            print(f"⚠️ メッセージ送信エラー: {e}")

async def setup(bot):
    await bot.add_cog(ServerLogCog(bot))