import discord
from discord.ext import commands
import random
import string
import io
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import json
import os
from datetime import timedelta
from discord import app_commands
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()

client = AsyncIOMotorClient(os.getenv("MONGO_URI"))
db = client["verify"]
verify_roles = db["roles"]


async def get_role(guild_id: int, panel_name: str):
    doc = await verify_roles.find_one({"_id": str(guild_id)})
    if not doc:
        return None
    return doc.get("panels", {}).get(panel_name)


async def set_role(guild_id: int, panel_name: str, role_id: int):
    await verify_roles.update_one(
        {"_id": str(guild_id)},
        {"$set": {f"panels.{panel_name}": role_id}},
        upsert=True
    )


async def get_all_panels():
    async for doc in verify_roles.find({}):
        yield doc["_id"], doc.get("panels", {})

class CodeModal(discord.ui.Modal, title="認証コードの入力"):
    def __init__(self, cog, user):
        super().__init__()
        self.cog = cog
        self.user = user
        self.add_item(discord.ui.TextInput(
            label="認証コードを入力",
            placeholder="例: ABCD1",
            max_length=10
        ))

    async def on_submit(self, interaction: discord.Interaction):
        input_code = self.children[0].value.strip().upper()
        verify_info = self.cog.verify_codes.get(self.user.id)

        if verify_info is None:
            await interaction.response.send_message(
                "<:warn:1394241229176311888> 認証データが見つかりません。もう一度 `/verify` から始めてください。",
                ephemeral=True
            )
            return

        code, guild_id, role_id = verify_info
        guild = self.cog.bot.get_guild(int(guild_id))
        member = guild.get_member(self.user.id)

        if input_code == code:
            if guild and member:
                role = guild.get_role(role_id)
                if role:
                    try:
                        await member.add_roles(role, reason="認証成功")
                        self.cog.verify_codes.pop(self.user.id, None)
                        await interaction.response.send_message(
                            f"<:check:1394240622310850580> 認証しました。",
                            ephemeral=True
                        )
                        return
                    except discord.Forbidden:
                        await interaction.response.send_message(
                            f"<:warn:1394241229176311888> 認証には成功しましたが、ロールを付与できませんでした。\n"
                            f"→ botのロールが `{role.name}` より上にあるか確認してください。",
                            ephemeral=True
                        )
                        return
                    except Exception as e:
                        await interaction.response.send_message(
                            f"<:warn:1394241229176311888> ロールの付与中に予期せぬエラーが発生しました。\n```{type(e).__name__}: {e}```",
                            ephemeral=True
                        )
                        return
            await interaction.response.send_message(
                "<:warn:1394241229176311888> サーバーまたはロール情報に問題があります。",
                ephemeral=True
            )
        else:
            # 認証失敗 → タイムアウト処理（1分）
            if member:
                try:
                    await member.timeout(discord.utils.utcnow() + timedelta(minutes=1), reason="認証失敗")
                    await interaction.response.send_message(
                        f"<:cross:1394240624202481705>認証に失敗しました。\n1分後にやり直してください。",
                        ephemeral=True
                    )
                except discord.Forbidden:
                    await interaction.response.send_message(
                        f"<:cross:1394240624202481705>認証に失敗しました。",
                        ephemeral=True
                    )
            else:
                await interaction.response.send_message(
                    f"<:cross:1394240624202481705>メンバー情報が取得できませんでした。",
                    ephemeral=True
                )

class CodeInputButton(discord.ui.Button):
    def __init__(self, cog, user):
        super().__init__(label="コードを入力", style=discord.ButtonStyle.success)
        self.cog = cog
        self.user = user

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("このボタンはあなた専用です。", ephemeral=True)
            return
        await interaction.response.send_modal(CodeModal(self.cog, self.user))

class VerifyStartButton(discord.ui.Button):
    def __init__(self, cog, panel_name: str):
        super().__init__(
            label="認証",
            style=discord.ButtonStyle.primary,
            custom_id=f"persistent_verify_button:{panel_name}"
        )
        self.cog = cog
        self.panel_name = panel_name

    async def callback(self, interaction: discord.Interaction):
        user = interaction.user
        guild = interaction.guild
        guild_id = guild.id
        panel_name = self.panel_name

        role_id = await get_role(guild.id, panel_name)

        if role_id is None:
            await interaction.response.send_message(
                f"<:warn:1394241229176311888>このパネルにはロールが設定されていません。",
                ephemeral=True
            )
            return

        role = guild.get_role(role_id)
        if role is None:
            await interaction.response.send_message(
                f"<:warn:1394241229176311888>設定された認証ロールが見つかりません。",
                ephemeral=True
            )
            return

        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))
        image = Image.new("RGB", (220, 100), (255, 255, 255))
        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.truetype("assets/arial.ttf", 40)
        except:
            font = ImageFont.load_default()
        draw.text((50, 30), code, font=font, fill=(0, 0, 0))
        for _ in range(5):
            draw.line(
                [(random.randint(0, 220), random.randint(0, 100)),
                 (random.randint(0, 220), random.randint(0, 100))],
                fill=(150, 150, 150), width=2
            )
        for _ in range(200):
            x, y = random.randint(0, 219), random.randint(0, 99)
            draw.point((x, y), fill=(random.randint(0, 255), 0, 0))
        image = image.filter(ImageFilter.GaussianBlur(0.7))

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        buffer.seek(0)

        self.cog.verify_codes[user.id] = (code, guild.id, role_id)

        view = discord.ui.View()
        view.add_item(CodeInputButton(self.cog, user))

        file = discord.File(buffer, filename="captcha.png")
        await interaction.response.send_message(
            content=f"この文字を読み取って記入してください。",
            file=file,
            view=view,
            ephemeral=True
        )

class VerifyView(discord.ui.View):
    def __init__(self, cog, panel_name: str):
        super().__init__(timeout=None)
        self.add_item(VerifyStartButton(cog, panel_name))

class VerifyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.verify_codes = {}

    @commands.hybrid_command(name="verify", description="認証ロールを設定または認証パネルを送信します。")
    @commands.has_permissions(manage_guild=True)
    @app_commands.rename(panel_name="パネル名", role="ロール")
    async def verify(self, ctx: commands.Context, panel_name: str, role: discord.Role = None):
        guild_id = str(ctx.guild.id)

        if role is not None:
            await set_role(ctx.guild.id, panel_name, role.id)
            await ctx.send(
                f"<:check:1394240622310850580> パネル `{panel_name}` にロール `{role.name}` を設定しました。",
                ephemeral=True
            )
        else:
            role_id = await get_role(ctx.guild.id, panel_name)
            if role_id is None:
                await ctx.send(
                    f"<:warn:1394241229176311888> パネル `{panel_name}` にロールが設定されていません。",
                    ephemeral=True
                )
                return

            embed = discord.Embed(
                description=f"<@&{role_id}> をもらうには認証してください。",
                color=discord.Color.green()
            )
            view = VerifyView(self, panel_name)
            await ctx.send(embed=embed, view=view)

    @verify.error
    async def verify_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(f"<:cross:1394240624202481705> このコマンドを使うにはサーバー管理権限が必要です。", ephemeral=True)

async def setup(bot):
    cog = VerifyCog(bot)
    await bot.add_cog(cog)
    async for guild_id, panels in get_all_panels():
        for panel_name in panels:
            bot.add_view(VerifyView(cog, panel_name))