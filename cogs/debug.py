import discord
from discord.ext import commands
from discord import app_commands
import platform
import psutil
import socket
import datetime

PROGRESS_EMOJIS = {
    0: "<:progress0:1433077684719587558>",
    1: "<:progress1:1433077492843020439>",
    2: "<:progress2:1433077494726135919>",
    3: "<:progress3:1433077496991191111>",
    4: "<:progress4:1433077498933018634>",
    5: "<:progress5:1433077501307129949>",
    6: "<:progress6:1433077503437832254>",
    7: "<:progress7:1433077505333530705>",
    8: "<:progress8:1433077507573415986>",
    9: "<:progress9:1433077509464916200>",
    10: "<:progress10:1433077511285112893>",
}

def progress_bar(percent: float) -> str:

    # 0〜100を0〜10.0スケールに
    scaled = percent / 10
    full_blocks = int(scaled)  # 完全に満タンのマス数
    remainder = scaled - full_blocks  # 次のマスの進み具合（0.0〜1.0）

    # 残り部分を10段階に丸め
    partial_level = int(round(remainder * 10))

    bar = ""
    for i in range(10):
        if i < full_blocks:
            bar += PROGRESS_EMOJIS[10]  # 満タン
        elif i == full_blocks and partial_level > 0:
            bar += PROGRESS_EMOJIS[partial_level]  # 部分的に埋まってる
        else:
            bar += PROGRESS_EMOJIS[0]  # 空
    return bar

class Debug(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ===== 親グループ =====
    @commands.hybrid_group(name="debug", description="Botのデバッグ情報を表示します。")
    @commands.has_permissions(administrator=True)
    async def debug(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.reply("使用方法: `/debug systeminfo` または `/debug performance` `/debug network`", ephemeral=True)

    # ===== systeminfo =====
    @debug.command(name="systeminfo", description="システム情報を表示します。")
    async def systeminfo(self, ctx: commands.Context):
        uname = platform.uname()
        cpu_count = psutil.cpu_count(logical=True)
        memory = psutil.virtual_memory()
        uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(psutil.boot_time())

        embed = discord.Embed(
            title="<:server:1433081722202882088>システム情報",
            color=discord.Color.blurple()
        )
        embed.add_field(name="OS", value=f"{uname.system} {uname.release}", inline=False)
        embed.add_field(name="アーキテクチャ", value=uname.machine, inline=True)
        embed.add_field(name="CPU", value=f"{uname.processor or '不明'} ({cpu_count} コア)", inline=True)
        embed.add_field(name="稼働時間", value=str(uptime).split('.')[0], inline=False)
        embed.add_field(name="メモリ", value=f"{memory.used / 1024**3:.2f} / {memory.total / 1024**3:.2f} GB 使用中", inline=False)
        embed.set_footer(text=f"Bot起動ホスト: {socket.gethostname()}")

        await ctx.reply(embed=embed)

    # ===== performance =====
    @debug.command(name="performance", description="CPU・メモリ・ディスク使用率を表示します。")
    async def performance(self, ctx: commands.Context):
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        uptime = datetime.datetime.now() - datetime.datetime.fromtimestamp(psutil.boot_time())

        embed = discord.Embed(
            title="<:performance:1433081987542945873>パフォーマンス情報",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )

        embed.add_field(
            name="CPU使用率",
            value=f"{progress_bar(cpu_percent)} **{cpu_percent:.1f}%**",
            inline=False
        )
        embed.add_field(
            name=f"メモリ使用率({memory.used / 1024**3:.2f} / {memory.total / 1024**3:.2f} GB)",
            value=f"{progress_bar(memory.percent)} **{memory.percent:.1f}%**",
            inline=False
        )
        embed.add_field(
            name="ディスク使用率",
            value=f"{progress_bar(disk.percent)} **{disk.percent:.1f}%**",
            inline=False
        )

        embed.add_field(name="稼働時間", value=str(uptime).split('.')[0], inline=False)

        await ctx.reply(embed=embed)

    # ===== network =====
    @debug.command(name="network", description="ネットワーク情報を表示します。")
    async def network(self, ctx: commands.Context):
        hostname = socket.gethostname()
        try:
            local_ip = socket.gethostbyname(hostname)
        except Exception:
            local_ip = "取得失敗"

        net_io = psutil.net_io_counters()
        sent = net_io.bytes_sent / 1024**2
        recv = net_io.bytes_recv / 1024**2

        embed = discord.Embed(
            title="<:ping:1399035063672504421>ネットワーク情報",
            color=discord.Color.orange()
        )
        embed.add_field(name="ホスト名", value=hostname, inline=False)
        embed.add_field(name="送信データ量", value=f"{sent:.2f} MB", inline=True)
        embed.add_field(name="受信データ量", value=f"{recv:.2f} MB", inline=True)

        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(Debug(bot))
