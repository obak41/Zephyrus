import discord
from discord.ext import commands
from discord import app_commands
from PIL import Image, ImageDraw, ImageFont
import io, aiohttp, os, random, textwrap
from motor.motor_asyncio import AsyncIOMotorClient
from discord import app_commands
import os
from dotenv import load_dotenv

# === MongoDB ===
load_dotenv()

mongo = AsyncIOMotorClient(os.getenv("MONGO_URI"))
db = mongo["welcomer"]
config_collection = db["guild_settings"]

# === 定数 ===
PRESET_BACKGROUNDS = {
    "preset1": "assets/welcomecardPreset1.jpg",
    "preset2": "assets/welcomecardPreset2.jpg",
    "preset3": "assets/welcomecardPreset3.jpg",
}
FONT_PATH = "assets/Corporate-Logo-Rounded-Bold-ver3.otf"
DEFAULT_COLOR = "#ffffff"


class Welcomer(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # =====================================================
    # 💬 カード生成
    # =====================================================

    # --- ヘルパー: 指定幅でテキストを折り返す ---
    def fit_text_lines(self, text: str, draw: ImageDraw.Draw, font: ImageFont.FreeTypeFont, max_width: int):
        """
        text を max_width に収まるように分割して行リストを返す（単語単位で折り返し）。
        """
        if not text:
            return [""]

        # try to split by whitespace and build lines
        words = text.split()
        lines = []
        current = ""
        for w in words:
            test = (current + " " + w).strip()
            bbox = draw.textbbox((0,0), test, font=font)
            w_width = bbox[2] - bbox[0]
            if w_width <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                # if single word itself too long, break by characters
                bbox_word = draw.textbbox((0,0), w, font=font)
                if bbox_word[2] - bbox_word[0] <= max_width:
                    current = w
                else:
                    # break extremely long word into chunks
                    chunk = ""
                    for ch in w:
                        t = chunk + ch
                        if draw.textbbox((0,0), t, font=font)[2] - draw.textbbox((0,0), t, font=font)[0] <= max_width:
                            chunk = t
                        else:
                            if chunk:
                                lines.append(chunk)
                            chunk = ch
                    if chunk:
                        current = chunk
                    else:
                        current = ""
        if current:
            lines.append(current)
        return lines

    # --- ヘルパー: フォントサイズを下げて指定行数・領域に収める ---
    def shrink_font_to_fit(self, draw: ImageDraw.Draw, text_lines: list, font_path: str, start_size: int, max_width: int, max_height: int, min_size: int = 12):
        """
        start_size からフォントサイズを下げつつ、text_lines を max_width×max_height に収まるサイズを返す。
        text_lines は最初は折り返し前の1行文字列（ここでは再折り返しで使うので join して渡す想定）。
        戻り値: (font, lines) — 実際に描画する font と行リスト
        """
        text = "\n".join(text_lines) if isinstance(text_lines, (list, tuple)) else text_lines
        size = start_size
        while size >= min_size:
            font = ImageFont.truetype(font_path, size)
            # wrap into lines that fit width
            lines = self.fit_text_lines(text, draw, font, max_width)
            # compute total height
            total_h = 0
            line_spacing = int(size * 0.15)
            for ln in lines:
                bbox = draw.textbbox((0,0), ln, font=font)
                h = bbox[3] - bbox[1]
                total_h += h + line_spacing
            if total_h <= max_height and all(draw.textbbox((0,0), ln, font=font)[2] - draw.textbbox((0,0), ln, font=font)[0] <= max_width for ln in lines):
                return font, lines
            size -= 2
        # 最小サイズでも入りきらない場合は強制的に切って省略
        font = ImageFont.truetype(font_path, min_size)
        lines = fit_text_lines(text, draw, font, max_width)
        # if still too tall, truncate lines
        line_spacing = int(min_size * 0.15)
        max_lines = max(1, max_height // (min_size + line_spacing))
        if len(lines) > max_lines:
            # keep allowed lines and ellipsize last
            keep = lines[:max_lines]
            last = keep[-1]
            # shorten last until it fits with ellipsis
            while draw.textbbox((0,0), last + "…", font=font)[2] - draw.textbbox((0,0), last + "…", font=font)[0] > max_width and last:
                last = last[:-1]
            keep[-1] = last + "…" if last else "…"
            return font, keep
        return font, lines

    # ------------- create_card の差し替え実装 -------------
    async def create_card(self, member: discord.Member, mode: str, config: dict):
        """ようこそ / さよなら カード生成（文字自動折返し＋縮小対応）"""
        bg_path = config.get("background", PRESET_BACKGROUNDS.get("preset1"))
        color = config.get("text_color", DEFAULT_COLOR)

        # 背景読み込み
        if os.path.exists(bg_path):
            bg = Image.open(bg_path).convert("RGBA").resize((700, 250))
        else:
            bg = Image.new("RGBA", (700, 250), (60, 60, 80, 255))

        draw = ImageDraw.Draw(bg)

        # アバター取得（非同期）
        avatar_bytes = None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(str(member.display_avatar.url)) as resp:
                    avatar_bytes = await resp.read()
        except Exception:
            avatar_bytes = None

        if avatar_bytes:
            try:
                avatar = Image.open(io.BytesIO(avatar_bytes)).resize((180, 180)).convert("RGBA")
            except Exception:
                avatar = Image.new("RGBA", (180, 180), (255,255,255,255))
        else:
            avatar = Image.new("RGBA", (180, 180), (255,255,255,255))

        # 丸く切り抜き
        mask = Image.new("L", avatar.size, 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((0, 0, avatar.size[0], avatar.size[1]), fill=255)
        avatar.putalpha(mask)
        bg.paste(avatar, (30, 35), avatar)

        # 色変換
        try:
            color_rgb = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
        except Exception:
            color_rgb = (255, 255, 255)

        # テキスト内容準備
        count = member.guild.member_count if member.guild else 0
        if mode == "welcome":
            line1 = f"{member.name}さん、"
            line2 = f"{member.guild.name}へようこそ！"
            line3 = f"あなたは{count}人目のメンバーです！"
        else:
            line1 = f"{member.name}さんが"
            line2 = f"{member.guild.name}から退出しました。"
            line3 = f"また戻ってきてね！"

        # テキスト描画領域設定（アバター右側の余白内に収める）
        text_area_x = 250
        text_area_w = 700 - text_area_x - 30  # 右マージン30
        # 各行に割り当てられる高さ（合計で text_area_h を超えないようにする）
        # 大行: line1、medium: line2、small: line3 を想定して個別に調整
        # line1: max 1 行, line2: max 2 行, line3: max 1 行（必要なら縮小＋折返し）
        line1_max_h = 60
        line2_max_h = 80
        line3_max_h = 40

        # フォントファイルの存在確認
        font_path = FONT_PATH if os.path.exists(FONT_PATH) else None
        if not font_path:
            # デフォルトのPILフォント fallback（サイズ自動は難しいが最低限表示）
            font_path = ImageFont.load_default().path if hasattr(ImageFont.load_default(), "path") else None
            # もしpath取れない場合は truetype 呼ばずに default Font を使う
            if not font_path:
                # その場合は単純描画して返す
                draw.text((text_area_x, 70), line1, fill=color_rgb)
                draw.text((text_area_x, 120), line2, fill=color_rgb)
                draw.text((text_area_x, 180), line3, fill=color_rgb)
                buf = io.BytesIO()
                bg.save(buf, "PNG")
                buf.seek(0)
                return discord.File(buf, filename=f"{mode}.png")

        # line1: 大見出し（1行）
        font1, lines1 = self.shrink_font_to_fit(draw, [line1], font_path, start_size=36, max_width=text_area_w, max_height=line1_max_h, min_size=18)
        # line2: 中見出し（最大2行）
        font2, lines2 = self.shrink_font_to_fit(draw, [line2], font_path, start_size=30, max_width=text_area_w, max_height=line2_max_h, min_size=14)
        # line3: 小見出し（1行）
        font3, lines3 = self.shrink_font_to_fit(draw, [line3], font_path, start_size=20, max_width=text_area_w, max_height=line3_max_h, min_size=12)

        # 垂直配置：line1 -> line2 -> line3 を順に描画。縦オフセット微調整
        y = 60
        spacing = 6
        for ln in lines1:
            draw.text((text_area_x, y), ln, font=font1, fill=color_rgb)
            h = draw.textbbox((0,0), ln, font=font1)[3] - draw.textbbox((0,0), ln, font=font1)[1]
            y += h + spacing
        y += 4  # 少し余白
        for ln in lines2:
            draw.text((text_area_x, y), ln, font=font2, fill=color_rgb)
            h = draw.textbbox((0,0), ln, font=font2)[3] - draw.textbbox((0,0), ln, font=font2)[1]
            y += h + spacing
        # line3 は下寄せ気味に（元デザインの y 値近く）
        # もし line3 行数が1行なら固定 y=180 相当にする
        y3_target = 180
        # ただし既に y が大きければそのまま続ける
        if y < y3_target:
            y = y3_target
        for ln in lines3:
            draw.text((text_area_x, y), ln, font=font3, fill=color_rgb)
            h = draw.textbbox((0,0), ln, font=font3)[3] - draw.textbbox((0,0), ln, font=font3)[1]
            y += h + spacing

        # 出力
        buf = io.BytesIO()
        bg.save(buf, "PNG")
        buf.seek(0)
        return discord.File(buf, filename=f"{mode}.png")

    # =====================================================
    # 👋 参加・退出イベント
    # =====================================================
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        config = await config_collection.find_one({"_id": member.guild.id}) or {}
        if not config.get("welcome_enabled", False):
            return

        channel_id = config.get("channel_id")
        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        file = await self.create_card(member, "welcome", config)
        await channel.send(content=f"{member.mention}", file=file)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        config = await config_collection.find_one({"_id": member.guild.id}) or {}
        if not config.get("goodbye_enabled", False):
            return

        channel_id = config.get("channel_id")
        if not channel_id:
            return

        channel = member.guild.get_channel(channel_id)
        if not channel:
            return

        file = await self.create_card(member, "goodbye", config)
        await channel.send(content=f"{member.mention}", file=file)

    # =====================================================
    # ⚙️ 設定コマンド
    # =====================================================
    @commands.hybrid_group(name="welcomer", description="ウェルカムカード設定")
    @commands.has_permissions(manage_guild=True)
    async def welcomer(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("使用方法: r!welcomer [welcome|goodbye|channel|edit-bg|edit-color|show-preview]", ephemeral=True)

    # --- 有効/無効設定 ---
    @welcomer.command(name="welcome", description="ようこそカードの設定をします。")
    @app_commands.rename(enable="有効")
    @commands.has_permissions(manage_guild=True)
    async def welcome_toggle(self, ctx, enable: bool):
        await config_collection.update_one(
            {"_id": ctx.guild.id},
            {"$set": {"welcome_enabled": enable}},
            upsert=True
        )
        await ctx.reply(f"<:check:1394240622310850580>ようこそカードを{'有効' if enable else '無効'}にしました。", ephemeral=True)

    @welcomer.command(name="goodbye", description="さようならカードの設定をします。")
    @app_commands.rename(enable="有効")
    @commands.has_permissions(manage_guild=True)
    async def goodbye_toggle(self, ctx, enable: bool):
        await config_collection.update_one(
            {"_id": ctx.guild.id},
            {"$set": {"goodbye_enabled": enable}},
            upsert=True
        )
        await ctx.reply(f"<:check:1394240622310850580>さようならカードを{'有効' if enable else '無効'}にしました。", ephemeral=True)

    # --- チャンネル設定 ---
    @welcomer.command(name="channel", description="カードの送信先を設定します。")
    @app_commands.rename(channel="チャンネル")
    @commands.has_permissions(manage_guild=True)
    async def set_channel(self, ctx, channel: discord.TextChannel):
        await config_collection.update_one(
            {"_id": ctx.guild.id},
            {"$set": {"channel_id": channel.id}},
            upsert=True
        )
        await ctx.reply(f"<:check:1394240622310850580>カード送信先を{channel.mention}に設定しました。", ephemeral=True)

    # --- 背景変更 ---
    @welcomer.command(name="edit-bg", description="カードの背景を変更します。")
    @app_commands.describe(image="推奨サイズ：700x250")
    @app_commands.rename(image="背景画像", preset="プリセット")
    @commands.has_permissions(manage_guild=True)
    @app_commands.choices(
        preset=[
            app_commands.Choice(name="プリセット1", value="preset1"),
            app_commands.Choice(name="プリセット2", value="preset2"),
            app_commands.Choice(name="プリセット3", value="preset3"),
        ]
    )
    async def edit_bg(
        self,
        ctx: commands.Context,
        preset: app_commands.Choice[str] = None,
        image: discord.Attachment = None
    ):
        """背景プリセットまたは画像を設定"""
        # --- 両方未指定 ---
        if not preset and not image:
            await ctx.reply(
                "<:cross:1394240624202481705> プリセットまたは画像のどちらかを指定してください。",
                ephemeral=True
            )
            return

        bg_path = None
        display_name = ""
        notice_text = ""

        # --- 両方指定された場合は画像を優先 ---
        if preset and image:
            notice_text = "<:warn:1394241229176311888> 両方指定されましたが、アップロード画像を優先します。\n"

        # --- 画像がある場合 ---
        if image:
            os.makedirs("backgrounds", exist_ok=True)
            filename = f"{ctx.guild.id}_{image.filename}"
            custom_path = os.path.join("backgrounds", filename)
            await image.save(custom_path)
            bg_path = custom_path
            display_name = image.filename

        # --- 画像がないがプリセットが指定されている場合 ---
        elif preset:
            bg_path = PRESET_BACKGROUNDS.get(preset.value, PRESET_BACKGROUNDS["preset1"])
            display_name = preset.name

        # --- MongoDBに保存 ---
        await config_collection.update_one(
            {"_id": ctx.guild.id},
            {"$set": {"background": bg_path}},
            upsert=True
        )

        # --- 応答メッセージ ---
        await ctx.reply(
            f"{notice_text}<:check:1394240622310850580>背景を `{display_name}` に設定しました。",
            ephemeral=True
        )



    # --- テキストカラー設定 ---
    @welcomer.command(name="edit-color", description="カードの文字色を変更します。")
    @app_commands.rename(hex_color="hexカラーコード")
    @commands.has_permissions(manage_guild=True)
    async def edit_color(self, ctx, hex_color: str):
        if not hex_color.startswith("#") or len(hex_color) != 7:
            await ctx.reply("<:cross:1394240624202481705>HEXカラー形式（例: `#ffffff`）で指定してください。", ephemeral=True)
            return

        await config_collection.update_one(
            {"_id": ctx.guild.id},
            {"$set": {"text_color": hex_color}},
            upsert=True
        )
        await ctx.reply(f"<:check:1394240622310850580>テキストカラーを `{hex_color}` に設定しました。", ephemeral=True)

    # --- プレビュー表示 ---
    @welcomer.command(name="show-preview", description="カードのプレビューを表示します。")
    async def show_preview(self, ctx):
        config = await config_collection.find_one({"_id": ctx.guild.id}) or {}
        dummy_member = ctx.guild.me
        file = await self.create_card(dummy_member, "welcome", config)
        await ctx.reply(file=file, ephemeral=True)

    @welcomer.error
    async def welcomer_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(f"<:cross:1394240624202481705> このコマンドを使うにはサーバー管理権限が必要です。", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Welcomer(bot))
