import discord
from discord.ext import commands
import datetime
import platform
import time

class UtilityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = time.time()

    @commands.hybrid_command(name="about", description="Botの情報を表示します。")
    async def about(self, ctx):
        uptime = datetime.timedelta(seconds=int(time.time() - self.start_time))
        shard_id = ctx.guild.shard_id if ctx.guild else 0
        embed = discord.Embed(
            title=f"<:info:1399034333284667422>Bot情報",
            color=discord.Color.blurple(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name=f"<:tag:1398952153242144788>Bot名", value=self.bot.user.name, inline=True)
        embed.add_field(name=f"<:spanner:1399035839324880958>バージョン", value="1.4", inline=True)
        embed.add_field(name=f"<:roles:1398955473797124107>開発チーム", value="Zephyrus Developers", inline=True)

        embed.add_field(name=f"<:ping:1399035063672504421>シャード", value=f"{shard_id + 1}/{self.bot.shard_count}", inline=True)
        embed.add_field(name=f"<:servers:1399035081074675774>サーバー数", value=f"{len(self.bot.guilds)}", inline=True)
        embed.add_field(name=f"<:roles:1398955473797124107>ユーザー数", value=f"{len(self.bot.users)}", inline=True)

        embed.add_field(name=f"<:ping:1399035063672504421>Ping", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        embed.add_field(name=f"<:check:1394240622310850580>起動時間", value=str(uptime), inline=True)
        embed.set_footer(text=f"Python {platform.python_version()} | discord.py {discord.__version__}")
        embed.set_thumbnail(url=self.bot.user.avatar.url if self.bot.user.avatar else None)

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(UtilityCog(bot))
