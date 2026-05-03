from discord.ext import commands
import discord

SUPPORT_SERVER_URL = "https://discord.gg/DKPj983cpb"
WEBPAGE_URL = "https://zephyrus-net.com" 

class GuildLogCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log_channel_id = 1399229118540812410

    async def send_log(self, embed: discord.Embed):
        log_channel = self.bot.get_channel(self.log_channel_id)
        if log_channel:
            try:
                await log_channel.send(embed=embed)
            except Exception as e:
                print(f"⚠️ ログ送信に失敗: {e}")

    def create_view(self):
        view = discord.ui.View()
        
        # サポートサーバー用ボタン
        support_button = discord.ui.Button(
            label="サポートサーバー",
            style=discord.ButtonStyle.link,
            url=SUPPORT_SERVER_URL,
        )
        
        # 新しく追加するボタン（例：ダッシュボードやWebサイトなど）
        webpage_button = discord.ui.Button(
            label="公式サイト",
            style=discord.ButtonStyle.link,
            url=WEBPAGE_URL,
        )
        
        view.add_item(support_button)
        view.add_item(webpage_button) # ボタンをViewに追加
        return view

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        # --- 1. 管理用ログ送信 ---
        embed = discord.Embed(
            color=discord.Color.green()
        )
        icon_url = guild.icon.url if guild.icon else None
        embed.set_author(name=f"{guild.name}(ID:{guild.id})に参加しました。", icon_url=icon_url)
        await self.send_log(embed)

        # --- 2. 導入サーバーへのあいさつ送信 ---
        target_channel = guild.system_channel
        
        if target_channel is None or not target_channel.permissions_for(guild.me).send_messages:
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    target_channel = channel
                    break

        if target_channel:
            try:
                greet_embed = discord.Embed(
                    title="Zephyrusを導入していただきありがとうございます！",
                    description=(
                        f"<:check:1394240622310850580> Zephyrusが{guild.name}に正常に追加されました！\n\n"
                        "コマンドは `/help` または `z!help` で確認できます。"
                    ),
                    color=discord.Color.blue()
                )
                view = self.create_view()
                await target_channel.send(embed=greet_embed, view=view)
            except Exception as e:
                print(f"⚠️ あいさつ送信に失敗 ({guild.name}): {e}")

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        embed = discord.Embed(
            color=discord.Color.red()
        )
        icon_url = guild.icon.url if guild.icon else None
        embed.set_author(name=f"{guild.name}(ID:{guild.id})から退出しました。", icon_url=icon_url)
        await self.send_log(embed)

async def setup(bot):
    await bot.add_cog(GuildLogCog(bot))