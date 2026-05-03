import discord
from discord.ext import commands
import traceback
import random
import string
import io
import datetime
import os

ERROR_TRACEBACK_CHANNEL_ID = 1394294521113612318
ERROR_LOG_DIR = "error_logs"
SUPPORT_SERVER_URL = "https://discord.gg/DKPj983cpb"

os.makedirs(ERROR_LOG_DIR, exist_ok=True)

class ErrorHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def generate_error_code(self, length=6):
        return ''.join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=length))

    def create_error_view(self):
        """サポートサーバーへの誘導ボタンを持つViewを作成"""
        view = discord.ui.View()
        button = discord.ui.Button(
            label="サポートサーバー",
            style=discord.ButtonStyle.link,
            url=SUPPORT_SERVER_URL,
            emoji="<:spanner:1399035839324880958>" # 適宜絵文字を変更してください
        )
        view.add_item(button)
        return view

    async def send_error_traceback(self, ctx_or_inter, error_id, error_text, filename, guild_name):
        channel = self.bot.get_channel(ERROR_TRACEBACK_CHANNEL_ID)
        safe_guild_name = (guild_name or "DM").replace(" ", "_").replace("/", "_")
        safe_filename = (filename or "Unknown").replace(" ", "_").replace("/", "_")
        file_name = f"errorTraceback-{safe_guild_name}-{safe_filename}-{error_id}.txt"

        # ローカル保存
        local_path = os.path.join(ERROR_LOG_DIR, file_name)
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(f"=== エラー情報 ===\n")
            f.write(f"サーバー: {guild_name or 'DM'}\n")
            f.write(f"ファイル/コマンド: {filename}\n")
            user = ctx_or_inter.user if hasattr(ctx_or_inter, "user") else ctx_or_inter.author
            f.write(f"ユーザー: {user} ({user.id})\n")
            f.write(f"発生日時: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("\n=== Traceback ===\n")
            f.write(error_text)

        file = discord.File(io.BytesIO(error_text.encode('utf-8')), filename=file_name)

        embed = discord.Embed(
            title=f"<:error:1394294289353277582> エラー発生（コード: {error_id}）",
            color=discord.Color.red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="サーバー", value=guild_name or "DM / 不明", inline=False)
        embed.add_field(name="ユーザー", value=f"{user} ({user.id})", inline=False)
        if hasattr(ctx_or_inter, "command") and ctx_or_inter.command:
            embed.add_field(name="コマンド", value=ctx_or_inter.command.qualified_name, inline=False)

        if channel:
            await channel.send(embed=embed, file=file)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if (hasattr(ctx.command, 'on_error') and callable(ctx.command.on_error)) or \
           (ctx.cog and hasattr(ctx.cog, 'cog_command_error') and ctx.cog.cog_command_error.__func__ is not commands.Cog.cog_command_error):
            return
        if isinstance(error, (commands.CommandNotFound, commands.MissingPermissions)):
            return

        error_id = self.generate_error_code()
        error_text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        guild_name = ctx.guild.name if ctx.guild else "DM"
        filename = ctx.command.qualified_name if ctx.command else "不明コマンド"

        await self.send_error_traceback(ctx, error_id, error_text, filename, guild_name)

        # 誘導ボタンViewを作成
        view = self.create_error_view()
        await ctx.send(
            f"<:error:1394294289353277582> コマンド実行中にエラーが発生しました。\nエラーコード: `{error_id}`",
            view=view,
            ephemeral=True if hasattr(ctx, 'interaction') else False
        )

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error):
        if isinstance(error, (discord.app_commands.errors.CommandNotFound, discord.app_commands.errors.MissingPermissions)):
            return

        error_id = self.generate_error_code()
        error_text = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        guild_name = interaction.guild.name if interaction.guild else "DM"
        command_name = interaction.command.name if interaction.command else "不明コマンド"

        await self.send_error_traceback(interaction, error_id, error_text, command_name, guild_name)

        # 誘導ボタンViewを作成
        view = self.create_error_view()
        try:
            msg = f"<:error:1394294289353277582> コマンド実行中にエラーが発生しました。\nエラーコード: `{error_id}`\n解決しない場合は以下のボタンから報告してください。"
            if interaction.response.is_done():
                await interaction.followup.send(msg, view=view, ephemeral=True)
            else:
                await interaction.response.send_message(msg, view=view, ephemeral=True)
        except discord.HTTPException:
            pass

async def setup(bot):
    await bot.add_cog(ErrorHandler(bot))