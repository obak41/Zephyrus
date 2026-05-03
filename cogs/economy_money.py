import discord
from discord.ext import commands
from discord import app_commands
from utils.economy_db import get_user, update_balance, log_transaction, get_logs
from utils.economy_utils import format_coin, create_embed, paginate, format_time
from discord.utils import utcnow
import math

class EconomyMoney(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ======================
    # 💵 残高確認
    # ======================
    @commands.hybrid_command(name="balance", description="自分または他人の所持金を確認します。", aliases=["bal"])
    @app_commands.rename(member="メンバー")
    async def balance(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        data = await get_user(ctx.guild.id, member.id)

        embed = create_embed(color=discord.Color.gold())
        embed.set_author(name=f"{member.display_name}の残高", icon_url=member.display_avatar.url)
        embed.add_field(name="<:wallet:1434903060282343518> 所持金", value=format_coin(data["wallet"]))
        embed.add_field(name="<:bank:1434903058948689951> 銀行", value=format_coin(data["bank"]))
        await ctx.reply(embed=embed, mention_author=False)

    # ======================
    # 🏦 銀行
    # ======================
    @commands.hybrid_group(name="bank", description="銀行の操作を行います。")
    async def bank(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.reply("使用方法: `z!bank deposit 金額` または `z!bank withdraw 金額`")

    @bank.command(name="deposit", description="所持金を銀行に預けます。", aliases=["dep"])
    @app_commands.rename(amount="金額")
    async def bank_deposit(self, ctx: commands.Context, amount: int):
        data = await get_user(ctx.guild.id, ctx.author.id)
        if amount <= 0:
            return await ctx.reply("<:cross:1394240624202481705> 正の数を入力してください。", ephemeral=True)
        if data["wallet"] < amount:
            return await ctx.reply("<:cross:1394240624202481705> 所持金が不足しています。", ephemeral=True)

        await update_balance(ctx.guild.id, ctx.author.id, wallet_delta=-amount, bank_delta=amount)
        await log_transaction(ctx.guild.id, ctx.author.id, ctx.author.id, amount, "銀行に預金")

        await ctx.reply(f"<:check:1394240622310850580> {format_coin(amount)}を銀行に預けました！")

    @bank.command(name="withdraw", description="金を銀行から引き出します。", aliases=["with"])
    @app_commands.rename(amount="金額")
    async def bank_withdraw(self, ctx: commands.Context, amount: int):
        data = await get_user(ctx.guild.id, ctx.author.id)
        if amount <= 0:
            return await ctx.reply("<:cross:1394240624202481705> 正の数を入力してください。", ephemeral=True)
        if data["bank"] < amount:
            return await ctx.reply("<:cross:1394240624202481705> 銀行残高が不足しています。", ephemeral=True)

        await update_balance(ctx.guild.id, ctx.author.id, wallet_delta=amount, bank_delta=-amount)
        await log_transaction(ctx.guild.id, ctx.author.id, ctx.author.id, -amount, "銀行から引き出し")

        await ctx.reply(f"<:check:1394240622310850580> {format_coin(amount)} を引き出しました！")

    # ======================
    # 💸 管理用: お金操作
    # ======================
    @commands.hybrid_group(name="money", description="お金に関する管理コマンドです。")
    async def money(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.reply("使用方法: `z!money add`, `z!money remove`, `z!money give`, `z!money log`")

    @money.command(name="add", description="指定したメンバーの残高を増やします。")
    @commands.has_permissions(manage_guild=True)
    @app_commands.rename(member="メンバー", amount="金額")
    async def money_add(self, ctx: commands.Context, member: discord.Member, amount: int):
        if amount <= 0:
            return await ctx.reply("<:cross:1394240624202481705> 正の数を入力してください。", ephemeral=True)

        await update_balance(ctx.guild.id, member.id, wallet_delta=amount)

        # 対象者のみに記録
        await log_transaction(
            guild_id=ctx.guild.id,
            actor_id=ctx.author.id,
            target_id=member.id,
            amount=amount,
            detail="管理者による残高追加",
            write_to=member.id
        )


        await ctx.reply(f"<:check:1394240622310850580> {member.display_name}に{format_coin(amount)}追加しました。", ephemeral=True)


    @money.command(name="remove", description="指定したメンバーの残高を減らします。")
    @commands.has_permissions(manage_guild=True)
    @app_commands.rename(member="メンバー", amount="金額")
    async def money_remove(self, ctx: commands.Context, member: discord.Member, amount: int):
        if amount <= 0:
            return await ctx.reply("<:cross:1394240624202481705> 正の数を入力してください。", ephemeral=True)

        data = await get_user(ctx.guild.id, member.id)
        if data["wallet"] < amount:
            return await ctx.reply(
            f"<:warn:1394241229176311888> {member.mention} の所持金が不足しています。\n"
            f"現在の所持金: {format_coin(data['wallet'])}", ephemeral=True
            )

        await update_balance(ctx.guild.id, member.id, wallet_delta=-amount)

        # 対象者のみに記録
        await log_transaction(
            guild_id=ctx.guild.id,
            actor_id=ctx.author.id,
            target_id=member.id,
            amount=-amount,
            detail="管理者による残高削除",
            write_to=member.id
        )


        await ctx.reply(f"<:check:1394240622310850580> {member.display_name}から{format_coin(amount)}削除しました。", ephemeral=True)


    @money.command(name="give", description="他のメンバーにお金を送金します。")
    @app_commands.rename(member="メンバー", amount="金額")
    async def money_give(self, ctx: commands.Context, member: discord.Member, amount: int):
        if member.id == ctx.author.id:
            return await ctx.reply("<:cross:1394240624202481705> 自分自身には送れません。", ephemeral=True)
        if amount <= 0:
            return await ctx.reply("<:cross:1394240624202481705> 正の数を入力してください。", ephemeral=True)

        sender_data = await get_user(ctx.guild.id, ctx.author.id)
        if sender_data["wallet"] < amount:
            return await ctx.reply("<:cross:1394240624202481705> 所持金が不足しています。", ephemeral=True)

        # 残高更新
        await update_balance(ctx.guild.id, ctx.author.id, wallet_delta=-amount)
        await update_balance(ctx.guild.id, member.id, wallet_delta=amount)

        # 双方にログ記録
        await log_transaction(
            guild_id=ctx.guild.id,
            actor_id=ctx.author.id,
            target_id=member.id,
            amount=-amount,
            detail=f"{member.mention}への送金",
            write_to=ctx.author.id
        )

        await log_transaction(
            guild_id=ctx.guild.id,
            actor_id=ctx.author.id,
            target_id=member.id,
            amount=amount,
            detail=f"{ctx.author.mention}からの受け取り",
            write_to=member.id
        )


        await ctx.reply(f"<:check:1394240622310850580> {member.mention}に{format_coin(amount)}を送金しました！")


    # ======================
    # 📜 取引ログ閲覧（5件/ページ）
    # ======================
    @money.command(name="log", description="最近の取引履歴を確認します。")
    @app_commands.rename(member="メンバー")
    async def money_log(self, ctx: commands.Context, member: discord.Member = None):
        member = member or ctx.author
        logs = await get_logs(ctx.guild.id, member.id, limit=50)

        if not logs:
            return await ctx.reply("<:warn:1394241229176311888> 取引履歴はありません。", ephemeral=True)

        pages = list(paginate(logs, per_page=5))
        page_index = 0

        def make_embed(page_index: int):
            page = pages[page_index]
            embed = create_embed(
                title=f"{member.display_name}の取引履歴 ({page_index + 1}/{len(pages)})",
                color=discord.Color.blue()
            )
            for log in page:
                actor = self.bot.get_user(log['actor_id'])
                target = self.bot.get_user(log['target_id'])
                actor_name = actor.display_name if actor else f"ID:{log['actor_id']}"
                target_name = target.display_name if target else f"ID:{log['target_id']}"
                timestamp = format_time(log['timestamp'])
                embed.add_field(
                    name=f"{format_coin(log['amount'])} | {timestamp}",
                    value=f"実行者: **{actor_name}**\n対象: **{target_name}**\n詳細: {log.get('detail', 'なし')}",
                    inline=False
                )
            return embed

        view = LogPaginatorView(make_embed, len(pages))
        await ctx.reply(embed=make_embed(0), view=view)

# ======================
# 🔄 ページ送りView
# ======================
class LogPaginatorView(discord.ui.View):
    def __init__(self, make_embed_func, total_pages: int):
        super().__init__(timeout=120)
        self.make_embed_func = make_embed_func
        self.total_pages = total_pages
        self.page_index = 0

    @discord.ui.button(emoji="<:prev:1401175547719192628>", style=discord.ButtonStyle.secondary)
    async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page_index = 0
        await interaction.response.edit_message(embed=self.make_embed_func(self.page_index), view=self)

    @discord.ui.button(emoji="<:leftSort:1401175053973848085>", style=discord.ButtonStyle.primary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page_index > 0:
            self.page_index -= 1
        await interaction.response.edit_message(embed=self.make_embed_func(self.page_index), view=self)

    @discord.ui.button(emoji="<:buttonDelete:1431291664261058650>", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

    @discord.ui.button(emoji="<:rightSort:1401174996574801950>", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page_index < self.total_pages - 1:
            self.page_index += 1
        await interaction.response.edit_message(embed=self.make_embed_func(self.page_index), view=self)

    @discord.ui.button(emoji="<:skip:1401175525069946920>", style=discord.ButtonStyle.secondary)
    async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page_index = self.total_pages - 1
        await interaction.response.edit_message(embed=self.make_embed_func(self.page_index), view=self)


async def setup(bot):
    await bot.add_cog(EconomyMoney(bot))
