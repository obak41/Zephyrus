import discord
from discord.ext import commands
from discord import app_commands
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

class stickyRoles(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = None  # MongoDB collection
        self.config_db = None  # 設定保存用コレクション


    async def cog_load(self):
        uri = os.getenv("MONGO_URI")
        client = AsyncIOMotorClient(uri)
        self.db = client["role_restore_db"]["roles"]
        self.config_db = client["role_restore_db"]["configs"]

    async def is_enabled(self, guild_id: int) -> bool:
        config = await self.config_db.find_one({"guild_id": guild_id})
        return config and config.get("enabled", False)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot or not await self.is_enabled(member.guild.id):
            return

        role_ids = [r.id for r in member.roles if r.name != "@everyone"]
        if role_ids:
            await self.db.update_one(
                {"guild_id": member.guild.id, "user_id": member.id},
                {"$set": {"roles": role_ids}},
                upsert=True
            )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot or not await self.is_enabled(member.guild.id):
            return

        data = await self.db.find_one_and_delete({
            "guild_id": member.guild.id,
            "user_id": member.id
        })

        if data and "roles" in data:
            roles = [member.guild.get_role(rid) for rid in data["roles"]]
            roles = [r for r in roles if r]

            added_roles = []
            failed_roles = []

            for role in roles:
                try:
                    await member.add_roles(role, reason="ロール復元機能による再付与")
                    added_roles.append(role.name)
                except discord.Forbidden:
                    failed_roles.append(role.name)
                except discord.HTTPException:
                    failed_roles.append(role.name)

            # DM 送信処理
            try:
                embed = discord.Embed(
                    title="おかえりなさい！",
                    description=f"{member.guild}から退出する前に付与されていたロールがあるようです。",
                    color=discord.Color.green()
                )

                if added_roles:
                    embed.add_field(
                        name=f"<:check:1394240622310850580>付与したロール",
                        value="\n".join(added_roles),
                        inline=False
                    )
                if failed_roles:
                    embed.add_field(
                        name=f"<:cross:1394240624202481705>付与できなかったロール",
                        value="\n".join(failed_roles),
                        inline=False
                    )

                embed.set_footer(icon_url=member.guild.icon.url, text=member.guild.name)
                await member.send(embed=embed)
            except discord.Forbidden:
                print(f"[DM失敗] {member} にDMを送信できませんでした。")



    @commands.hybrid_group(name="sticky-roles", description="ロール復元機能の設定を変更します。")
    @commands.has_guild_permissions(administrator=True)
    async def rolerestore(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.reply("使用法: `z!sticky-roles enable` または `z!sticky-roles disable`")

    @rolerestore.command(name="enable", with_app_command=True, description="ロール復元機能を有効にします。")
    @commands.has_guild_permissions(administrator=True)
    async def rolerestore_on(self, ctx: commands.Context):
        await self.config_db.update_one(
            {"guild_id": ctx.guild.id},
            {"$set": {"enabled": True}},
            upsert=True
        )
        await ctx.reply("<:check:1394240622310850580>ロール復元機能を**有効**にしました。")

    @rolerestore.command(name="disable", with_app_command=True, description="ロール復元機能を無効にします。")
    @commands.has_guild_permissions(administrator=True)
    async def rolerestore_off(self, ctx: commands.Context):
        await self.config_db.update_one(
            {"guild_id": ctx.guild.id},
            {"$set": {"enabled": False}},
            upsert=True
        )
        await ctx.reply("<:check:1394240622310850580>ロール復元機能を**無効**にしました。")

    @rolerestore_on.error
    async def rolerestore_on_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("<:cross:1394240624202481705>このコマンドを使用するには管理者権限が必要です。")
        else:
            await ctx.reply(f"<:cross:1394240624202481705>エラーが発生しました: {error}")

    @rolerestore_off.error
    async def rolerestore_off_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("<:cross:1394240624202481705>このコマンドを使用するには管理者権限が必要です。")
        else:
            await ctx.reply(f"<:cross:1394240624202481705>エラーが発生しました: {error}")

async def setup(bot):
    await bot.add_cog(stickyRoles(bot))
