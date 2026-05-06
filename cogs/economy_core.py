import discord
from discord.ext import commands
from discord import app_commands
from utils.economy_db import users, get_user, codes, update_balance
from utils.economy_utils import format_coin, create_embed
from discord.utils import utcnow
from utils.economy_settings import set_cooldown, reset_guild_settings, get_guild_settings
from datetime import datetime, timedelta, timezone

COOLDOWN_CATEGORIES = {
    "work": "仕事",
    "fish": "魚釣り",
    "rob": "強盗（プレイヤー）",
    "crime": "犯罪",
    "bankrob": "銀行強盗",
    "beg": "乞食",
}

class ConfirmView(discord.ui.View):
    def __init__(self, author: discord.Member, on_confirm):
        super().__init__(timeout=30)
        self.author = author
        self.on_confirm = on_confirm

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            return False
        return True

    @discord.ui.button(label="はい", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.on_confirm(interaction)
        self.stop()

    @discord.ui.button(label="いいえ", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="キャンセルしました。",
            view=None
        )
        self.stop()

class EconomyCore(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ======================
    # ⚙️ /ec admin
    # ======================
    @commands.hybrid_group(name="ec", description="経済システムの管理・統計コマンドです。")
    async def ec(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.reply("使用方法: `r!ec stats`, `r!ec cooldowns`, `r!ec leaderboard`, `r!ec redeem`\n"
            "`r!ec set-cooldown (種類) (時間)`, `r!ec check-cooldown`, `r!clear-cooldown (ユーザー) (種類)`, `r!reset-cooldown`, `r!reset-leaderboard`, `r!reset-user (ユーザー)`, `r!reset-economy`")

    @ec.command(name="set-cooldown", description="クールダウン時間を設定します。", aliases=["sc"])
    @commands.has_permissions(manage_guild=True)
    @app_commands.rename(category="クールダウンの種類", minutes="クールダウン時間")
    @app_commands.describe(minutes="分単位")
    @app_commands.choices(
        category=[
            app_commands.Choice(name=label, value=key)
            for key, label in COOLDOWN_CATEGORIES.items()
        ]
    )
    async def ec_set_cooldown(
        self,
        ctx: commands.Context,
        category: str,
        minutes: int
    ):
        if minutes < 0:
            await ctx.reply("<:cross:1394240624202481705> 正の数で入力してください。")
            return

        seconds = minutes * 60  # 🔹ここで変換

        await set_cooldown(ctx.guild.id, category, seconds)

        label = COOLDOWN_CATEGORIES.get(category, category)

        if minutes == 0:
            msg = "削除しました"
        else:
            msg = f"**{minutes}分**に設定しました"
        await ctx.reply(
            f"<:check:1394240622310850580> **{label}**のクールダウンを{msg}"
        )
        
    @ec.command(name="check-cooldown", description="サーバーのクールダウン設定を確認します。", aliases=["cc"])
    @commands.has_permissions(manage_guild=True)
    async def ec_check_cooldown(self, ctx: commands.Context):
        settings = await get_guild_settings(ctx.guild.id)
        cds = settings.get("cooldowns", {})

        embed = create_embed(
            title="サーバークールダウン設定",
            color=discord.Color.blurple()
        )

        if not cds:
            embed.description = "現在、設定されているクールダウンはありません。"
        else:
            lines = []
            for key, seconds in cds.items():
                label = COOLDOWN_CATEGORIES.get(key, key)
                lines.append(f"**{label}**: {seconds // 60} 分")
            embed.description = "\n".join(lines)

        await ctx.reply(embed=embed)

    @ec.command(name="clear-cooldown", description="ユーザーのクールダウンを削除します。", aliases=["clc"])
    @commands.has_permissions(manage_guild=True)
    @app_commands.rename(category="クールダウンの種類", user="ユーザー")
    @app_commands.choices(
        category=[
            app_commands.Choice(name=label, value=key)
            for key, label in COOLDOWN_CATEGORIES.items()
        ]
    )
    async def ec_clear_cooldown(
        self,
        ctx: commands.Context,
        user: discord.Member,
        category: str
    ):
        if category not in COOLDOWN_CATEGORIES:
            await ctx.reply("<:cross:1394240624202481705> 無効なクールダウンカテゴリです。")
            return

        await users.update_one(
            {"_id": f"{ctx.guild.id}-{user.id}"},
            {"$unset": {f"cooldowns.{category}": ""}}
        )

        await ctx.reply(
            f"<:check:1394240622310850580> {user.mention}のクールダウン**{COOLDOWN_CATEGORIES[category]}**を削除しました。"
        )

    @ec.command(name="reset-cooldown", description="サーバーのクールダウン設定をリセットします。", aliases=["rc"])
    @commands.has_permissions(manage_guild=True)
    async def ec_reset_cooldown(self, ctx: commands.Context):
        async def confirmed(interaction: discord.Interaction):
            await reset_guild_settings(ctx.guild.id)
            await interaction.response.edit_message(
                content="<:check:1394240622310850580> サーバーのクールダウン設定を全てリセットしました。",
                view=None
            )

        view = ConfirmView(ctx.author, confirmed)
        await ctx.reply(
            "<:warn:1394241229176311888> サーバーのクールダウン設定をリセットします。よろしいですか？",
            view=view
        )

    @ec.command(name="reset-leaderboard", description="リーダーボードをリセットします。", aliases=["rl"])
    @commands.has_permissions(manage_guild=True)
    async def ec_reset_leaderboard(self, ctx: commands.Context):

        async def confirmed(interaction: discord.Interaction):
            await users.update_many(
                {"_id": {"$regex": f"^{ctx.guild.id}-"}},
                {"$set": {"stats": {}}}
            )
            await interaction.response.edit_message(
                content="<:check:1394240622310850580> リーダーボード（統計）をリセットしました。",
                view=None
            )

        view = ConfirmView(ctx.author, confirmed)
        await ctx.reply(
            "<:warn:1394241229176311888> ランキング統計をリセットします。よろしいですか？",
            view=view
        )

    @ec.command(name="reset-user", description="ユーザーの経済データをリセットします。", aliases=["ru"])
    @app_commands.rename(user="ユーザー")
    @commands.has_permissions(manage_guild=True)
    async def ec_reset_user(
        self,
        ctx: commands.Context,
        user: discord.Member
    ):

        async def confirmed(interaction: discord.Interaction):
            await users.delete_one({"_id": f"{ctx.guild.id}-{user.id}"})
            await interaction.response.edit_message(content=f"<:check:1394240622310850580> {user.mention}の経済データをリセットしました。", view=None)
        
        view = ConfirmView(ctx.author, confirmed)
        await ctx.reply(
            f"<:warn:1394241229176311888> {user.mention}の経済データをリセットします。よろしいですか？",
            view=view
        )


    @ec.command(name="reset-economy", description="サーバーの経済データを全てリセットします。", aliases=["re"])
    @commands.has_permissions(manage_guild=True)
    async def ec_reset_economy(self, ctx: commands.Context):

        async def confirmed(interaction: discord.Interaction):
            await users.delete_many({"_id": {"$regex": f"^{ctx.guild.id}-"}})
            await reset_guild_settings(ctx.guild.id)

            await interaction.response.edit_message(
                content="<:check:1394240622310850580> このサーバーの経済データを全てリセットしました。", view=None
            )

        view = ConfirmView(ctx.author, confirmed)
        await ctx.reply(
            "<:warn:1394241229176311888> このサーバーの経済データをリセットします。よろしいですか？",
            view=view
        )

    # ======================    
    # 📊 /ec stats
    # ======================
    @ec.command(name="stats", description="あなたの経済統計を表示します。", aliases=["s"])
    async def ec_stats(self, ctx: commands.Context):
        user = await get_user(ctx.guild.id, ctx.author.id)

        job_info = user.get("job", {"title": "未就業", "worked": 0})
        job_title = job_info.get("title", "未就業")
        worked = job_info.get("worked", 0)
        total_salary = user.get("total_salary", 0)
        collections = user.get("collections", {})

        if not isinstance(collections, dict):
            collections = {}

        if collections:
            collections_text = "\n".join(
                f"• {name}"
                for name, count in collections.items()
            )
        else:
            collections_text = "なし"

        stats = user.get("stats", {
            "fish": 0,
            "crime": 0,
            "police": 0,
            "beg": 0,
            "scratch": 0,
            "lottery": 0,
            "badge": 0
        })

        embed = discord.Embed(
            color=discord.Color.gold()
        )
        embed.add_field(
            name="<:graph:1437787157002584186> 一番上の仕事",
            value=f"{job_title}",
            inline=False
        )
        embed.add_field(
            name="<:walking:1437788265187901522> 勤務回数",
            value=f"{worked} 回",
            inline=True
        )
        embed.add_field(
            name="<:wallet:1434903060282343518> これまでに働いて得た給料",
            value=f"{format_coin(total_salary)}",
            inline=True
        )
        embed.add_field(
            name="<:fishing:1437787154645520496> 魚を釣った回数",
            value=f"{stats.get('fish', 0)} 回",
            inline=True
        )
        embed.add_field(
            name="<:criminal:1437787152631988346> 強盗に成功した回数",
            value=f"{stats.get('crime', 0)} 回",
            inline=True
        )
        embed.add_field(
            name="<:police:1437787151151661096> 犯罪件数",
            value=f"{stats.get('police', 0)} 件",
            inline=True
        )
        embed.add_field(
            name="<:beg:1437787146059513889> 乞食回数",
            value=f"{stats.get('beg', 0)} 回",
            inline=True
        )
        embed.add_field(
            name="<:ticket:1414217916206813337> スクラッチカードを買った枚数",
            value=f"{stats.get('scratch', 0)} 枚",
            inline=True
        )
        embed.add_field(
            name="<:ticket:1414217916206813337> 宝くじを買った枚数",
            value=f"{stats.get('lottery', 0)} 枚",
            inline=True
        )
        embed.add_field(
            name="<:badge:1437787149431996537> 獲得した収集品",
            value=f"{collections_text}",
            inline=True
        )

        embed.set_author(name=f"{ctx.author.display_name}の経済統計", icon_url=ctx.author.display_avatar.url)
        await ctx.reply(embed=embed)

    # ======================
    # 🏆 /ec leaderboard
    # ======================
    @ec.command(name="leaderboard", description="資産ランキングを表示します。", aliases=["l"])
    async def ec_leaderboard(self, ctx: commands.Context):
        cursor = users.find({"_id": {"$regex": f"^{ctx.guild.id}-"}})
        data = []
        async for user in cursor:
            total = user.get("wallet", 0) + user.get("bank", 0)
            user_id = int(user["_id"].split("-")[1])
            data.append((user_id, total))

        data.sort(key=lambda x: x[1], reverse=True)
        top10 = data[:10]

        embed = create_embed(title="🏆 資産ランキング TOP 10", color=discord.Color.gold())
        for i, (uid, total) in enumerate(top10, start=1):
            member = ctx.guild.get_member(uid)
            name = member.display_name if member else f"Unknown ({uid})"
            embed.add_field(name=f"{i}. {name}", value=f"{format_coin(total)}", inline=False)

        await ctx.reply(embed=embed)

    # ======================
    # ⏰ クールダウン確認
    # ======================
    @ec.command(name="cooldowns", description="現在のクールダウン状態を確認します。", aliases=["c"])
    async def ec_cooldowns(self, ctx: commands.Context):
        user = await get_user(ctx.guild.id, ctx.author.id)
        cooldowns = user.get("cooldowns", {})
        now = utcnow().timestamp()

        embed = create_embed(title="⏰ クールダウン時間", color=discord.Color.blurple())

        lines = []
        for key, label in COOLDOWN_CATEGORIES.items():
            expires = cooldowns.get(key)
            if not expires:
                status = "<:success:1394240622310850580> 準備完了"
            else:
                remaining = int(expires - now)
                if remaining > 0:
                    status = f"<:failed:1394240624202481705> <t:{int(expires)}:R>"
                else:
                    status = "<:success:1394240622310850580> 準備完了"

            lines.append(f"{label}: {status}")

        embed.description = "\n".join(lines)
        embed.set_footer(text=f"{ctx.author.display_name}のクールダウン情報", icon_url=ctx.author.display_avatar.url)
        await ctx.reply(embed=embed, mention_author=False)

    # ======================
    # 🎁 /ec redeem
    # ======================
    @ec.command(name="redeem", description="ギフトコードを使用して特典を受け取ります。")
    @app_commands.rename(code="コード")
    async def ec_redeem(self, ctx: commands.Context, code: str):
        
        code_data = await codes.find_one({"_id": code})

        if not code_data:
            await ctx.reply("<:cross:1394240624202481705> 無効なコードです。", ephemeral=True)
            return

        # 🕒 有効期限チェック
        if "expires_at" in code_data and code_data["expires_at"]:
            # MongoDBから取得したdatetimeにUTCタイムゾーンを付与して比較
            expire_dt = code_data["expires_at"].replace(tzinfo=timezone.utc)
            if discord.utils.utcnow() > expire_dt:
                await ctx.reply("<:cross:1394240624202481705> このコードは有効期限が切れています。", ephemeral=True)
                return

        # 重複使用チェック（1人1回まで）
        if ctx.author.id in code_data.get("claimed_users", []):
            await ctx.reply("<:cross:1394240624202481705> このコードは使用済みです。", ephemeral=True)
            return

        # --- 特典付与処理 ---
        reward_type = code_data.get("reward_type")
        reward_value = code_data.get("reward_value")
        reward_amount = code_data.get("amount", 1)

        if reward_type == "money":
            await update_balance(ctx.guild.id, ctx.author.id, wallet_delta=reward_value)
            result_msg = f"<:check:1394240622310850580> **{format_coin(reward_value)}** を獲得しました！"
            
        elif reward_type == "item":
            # ユーザーデータの取得（現在の所持数を確認するため）
            from utils.economy_db import get_user
            user_data = await get_user(ctx.guild.id, ctx.author.id)
            
            item_id = reward_value
            current_count = user_data.get("inventory", {}).get(item_id, 0)
            max_count = ITEMS[item_id]["max"]
            item_name = ITEMS[item_id]["name"]
            item_price = ITEMS[item_id]["price"]

            # 空き容量の計算
            can_receive = max(0, max_count - current_count)
            
            if can_receive >= reward_amount:
                # すべてアイテムとして受け取れる場合
                await update_inventory(ctx.guild.id, ctx.author.id, item_id, reward_amount)
                result_msg = f"<:check:1394240622310850580> アイテム **{item_name}** ×{reward_amount} を獲得しました！"
            else:
                # 一部または全部が溢れる場合
                overflow_count = reward_amount - can_receive
                compensation_money = overflow_count * item_price
                
                # 持てる分だけアイテムを付与
                if can_receive > 0:
                    await update_inventory(ctx.guild.id, ctx.author.id, item_id, can_receive)
                
                # 溢れた分をお金に変換して付与
                await update_balance(ctx.guild.id, ctx.author.id, wallet_delta=compensation_money)
                
                if can_receive > 0:
                    result_msg = (f"<:check:1394240622310850580> **{item_name}** ×{can_receive} を獲得しました！\n"
                                 f"<:warn:1394241229176311888> 上限を超える {overflow_count}個分は **{format_coin(compensation_money)}** に変換されました。")
                else:
                    result_msg = (f"<:warn:1394241229176311888> **{item_name}** は既に上限まで所持しているため、\n"
                                 f"特典は **{format_coin(compensation_money)}** に変換されました！")

        else:
            await ctx.reply("<:cross:1394240624202481705> 特典タイプが不明です。")
            return

        # DB更新（使用済みリストにユーザーIDを追加するだけ）
        await codes.update_one(
            {"_id": code},
            {"$push": {"claimed_users": ctx.author.id}}
        )

        await ctx.reply(result_msg)

    @ec_set_cooldown.error
    async def ec_set_cooldown_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(f"<:cross:1394240624202481705> このコマンドを使うには管理者権限が必要です。", ephemeral=True)
    @ec_check_cooldown.error
    async def ec_check_cooldown_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(f"<:cross:1394240624202481705> このコマンドを使うには管理者権限が必要です。", ephemeral=True)
    @ec_clear_cooldown.error
    async def ec_clear_cooldown_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(f"<:cross:1394240624202481705> このコマンドを使うには管理者権限が必要です。", ephemeral=True)
    @ec_reset_cooldown.error
    async def ec_reset_cooldown_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(f"<:cross:1394240624202481705> このコマンドを使うには管理者権限が必要です。", ephemeral=True)
    @ec_reset_leaderboard.error
    async def ec_reset_leaderboard_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(f"<:cross:1394240624202481705> このコマンドを使うには管理者権限が必要です。", ephemeral=True)
    @ec_reset_user.error
    async def ec_reset_user_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(f"<:cross:1394240624202481705> このコマンドを使うには管理者権限が必要です。", ephemeral=True)
    @ec_reset_economy.error
    async def ec_reset_economy_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply(f"<:cross:1394240624202481705> このコマンドを使うには管理者権限が必要です。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(EconomyCore(bot))
