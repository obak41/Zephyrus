from discord.ext import commands
import discord
import time

class PingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="ping", description="Botの応答速度を表示します")
    async def ping(self, ctx):
        ws_ping = round(self.bot.latency * 1000)

        start = time.perf_counter()
        await self.bot.application_info()  # APIエンドポイントへのリクエスト
        end = time.perf_counter()
        api_ping = round((end - start) * 1000)

        await ctx.send(f"WebSocket: `{ws_ping}ms`\nAPI: `{api_ping}ms`")

async def setup(bot):
    await bot.add_cog(PingCog(bot))
