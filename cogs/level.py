import discord
from discord.ext import commands
from discord import app_commands, ui
import os
import math
import random
import time
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont, ImageOps
import io
import aiohttp
from dotenv import load_dotenv

load_dotenv()

# DB設定
mongo_client = AsyncIOMotorClient(os.getenv("MONGO_URI"))
db = mongo_client["level"]
xp_col = db["xp"]
config_col = db["config"]

class RoleAddModal(ui.Modal, title="報酬ロールの追加"):
    level = ui.TextInput(label="設定するレベル", placeholder="例: 5", min_length=1, max_length=3)

    def __init__(self, original_view):
        super().__init__()
        self.original_view = original_view # 名前を統一

    async def on_submit(self, interaction: discord.Interaction):
        if not self.level.value.isdigit():
            return await interaction.response.send_message("レベルを入力してください。", ephemeral=True)
        
        # 管理画面のメッセージを保存しておく
        base_message = interaction.message 
        
        # ロール選択用のセレクトメニューを作成
        view = ui.View()
        select = ui.RoleSelect(placeholder=f"レベル {self.level.value} に付与するロールを選択...", max_values=1)
        
        async def select_callback(inter: discord.Interaction):
            role = select.values[0]
            
            # --- 重複チェックの追加 ---
            conf = await config_col.find_one({"_id": inter.guild.id})
            roles_config = conf.get("roles", {}) if conf else {}
            
            for lv, rid in roles_config.items():
                if str(rid) == str(role.id):
                    if lv != self.level.value:
                        return await inter.response.send_message(
                            f"<:warn:1394241229176311888> このロールはすでに **レベル {lv}** の報酬として設定されています。重複して設定することはできません。", 
                            ephemeral=True
                        )
            # ------------------------

            # DB更新
            await config_col.update_one(
                {"_id": inter.guild.id},
                {"$set": {f"roles.{self.level.value}": str(role.id)}},
                upsert=True
            )

            # 管理画面の更新
            new_embed = await self.original_view.create_embed()
            if base_message:
                await base_message.edit(embed=new_embed, view=self.original_view)

            await inter.response.edit_message(
                content=f"<:check:1394240622310850580> レベル {self.level.value} に {role.mention} を追加しました。", 
                view=None
            )
            
        select.callback = select_callback
        view.add_item(select)
        
        await interaction.response.send_message(
            f"レベル **{self.level.value}** に設定するロールを選んでください。", 
            view=view, 
            ephemeral=True
        )

# --- 削除用セレクトメニュー専用View ---
class RoleDeleteView(ui.View):
    def __init__(self, interaction: discord.Interaction, roles_config, original_view):
        super().__init__(timeout=None)
        self.original_view = original_view
        # 元の管理画面メッセージのIDを保持しておく
        self.base_message = interaction.message 
        
        options = []
        for lv, rid in sorted(roles_config.items(), key=lambda x: int(x[0])):
            role = interaction.guild.get_role(int(rid))
            role_name = role.name if role else f"不明なロール (ID: {rid})"
            options.append(discord.SelectOption(label=f"レベル {lv}", value=lv, description=f"設定中: {role_name}"))

        select = ui.Select(placeholder="削除するロールを選択...", options=options)

        async def select_callback(inter: discord.Interaction):
            lv_to_delete = select.values[0]
            # DBから削除
            await config_col.update_one(
                {"_id": inter.guild.id},
                {"$unset": {f"roles.{lv_to_delete}": ""}}
            )

            # --- 更新処理の修正 ---
            new_embed = await self.original_view.create_embed()
            
            try:
                await self.base_message.edit(embed=new_embed, view=self.original_view)
            except Exception as e:
                print(f"Update failed: {e}")

            await inter.response.edit_message(
                content=f"<:check:1394240622310850580> レベル {lv_to_delete} の設定を削除しました。", 
                view=None
            )

        select.callback = select_callback
        self.add_item(select)

class StackSelect(discord.ui.Select):
    def __init__(self, current_stack: bool, original_view):
        self.original_view = original_view
        
        # 画像に基づいた選択肢の設定
        options = [
            discord.SelectOption(
                label="ロールをスタックする",
                value="True",
                description="過去に付与したロールを残します。",
                emoji="<:layer:1479499471409905674>",
                default=current_stack
            ),
            discord.SelectOption(
                label="ロールをスタックしない",
                value="False",
                description="過去に付与したロールは残りません。",
                emoji="<:clear:1479499469593641012>",
                default=not current_stack
            )
        ]
        super().__init__(placeholder="スタック設定", options=options, min_values=1, max_values=1, row=0)

    async def callback(self, interaction: discord.Interaction):
        # 選択された値に応じて真偽値を設定
        is_stack = self.values[0] == "True"
        
        # DBの更新処理
        await config_col.update_one(
            {"_id": interaction.guild.id},
            {"$set": {"stack_roles": is_stack}},
            upsert=True
        )
        
        # 管理画面（Embed）を最新の状態に更新
        new_embed = await self.original_view.create_embed()
        view = LevelRoleView(self.original_view.bot, interaction.guild.id, is_stack)
        await interaction.response.edit_message(embed=new_embed, view=view)

# --- メイン管理画面View ---
class LevelRoleView(ui.View):
    def __init__(self, bot, guild_id, stack_status, author_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.author_id = author_id
        self.add_item(StackSelect(stack_status, self))

    # このView内のすべてのコンポーネントに適用されるチェック
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            return False
        return True

    async def create_embed(self):
        conf = await config_col.find_one({"_id": self.guild_id})
        roles_config = conf.get("roles", {}) if conf else {}
        # DBから最新のスタック設定を取得
        stack_status = conf.get("stack_roles", True) if conf else True
        
        embed = discord.Embed(title="<:spanner:1399035839324880958> 報酬ロール設定", color=0x2b2d31)
        
        # ロール一覧のテキスト作成
        if roles_config:
            sorted_roles = sorted(roles_config.items(), key=lambda x: int(x[0]))
            roles_text = "\n".join([f"レベル {lv} ： <@&{rid}>" for lv, rid in sorted_roles])
        else:
            roles_text = "設定されているロールはありません。"
            
        # スタック設定の状態を分かりやすく表示
        stack_text = "有効" if stack_status else "無効"
        
        embed.description = f"ロールのスタック:{stack_text}\n### 現在のロール設定\n{roles_text}"
        return embed

    @ui.button(label="ロールを追加", emoji="<:buttonPlus:1444665079776808971>", style=discord.ButtonStyle.primary, row=1)
    async def add_role(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(RoleAddModal(self))

    @ui.button(label="ロールを削除", emoji="<:buttonMinus:1444665078015066182>", style=discord.ButtonStyle.danger, row=1)
    async def remove_role(self, interaction: discord.Interaction, button: ui.Button):
        conf = await config_col.find_one({"_id": interaction.guild.id})
        roles_config = conf.get("roles", {}) if conf else {}
        if not roles_config:
            return await interaction.response.send_message("削除できるロールがありません。", ephemeral=True)
        await interaction.response.send_message("削除したいロールを選んでください。", view=RoleDeleteView(interaction, roles_config, self), ephemeral=True)

# --- XPブースト追加用Modal ---
class BoostAddModal(ui.Modal, title="経験値ブーストロールの追加"):
    multiplier = ui.TextInput(
        label="倍率", 
        placeholder="例: 1.5 や 2.0 (1.0以上を入力)", 
        min_length=1, 
        max_length=4
    )

    def __init__(self, original_view):
        super().__init__()
        self.original_view = original_view

    async def on_submit(self, interaction: discord.Interaction):
        # 数値チェック
        try:
            val = float(self.multiplier.value)
            if val < 1.0:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("1.0以上の数値を入力してください（例: 1.5）。", ephemeral=True)
        
        base_message = interaction.message 
        
        # ロール選択View
        view = ui.View()
        select = ui.RoleSelect(placeholder=f"{val}倍のブーストを適用するロールを選択...", max_values=1)
        
        async def select_callback(inter: discord.Interaction):
            role = select.values[0]
            
            # --- 重複チェックの追加 ---
            conf = await config_col.find_one({"_id": inter.guild.id})
            boosts_config = conf.get("role_boosts", {}) if conf else {}
            
            # すでにそのロールに別の倍率が設定されているか確認
            if str(role.id) in boosts_config:
                current_m = boosts_config[str(role.id)]
                return await inter.response.send_message(
                    f"<:warn:1394241229176311888> {role.mention} にはすでに **{current_m}倍** のブーストが設定されています。",
                    ephemeral=True
                )
            # ------------------------

            # DB更新
            await config_col.update_one(
                {"_id": inter.guild.id},
                {"$set": {f"role_boosts.{role.id}": val}},
                upsert=True
            )

            # 管理画面の更新
            new_embed = await self.original_view.create_embed()
            if base_message:
                await base_message.edit(embed=new_embed, view=self.original_view)

            await inter.response.edit_message(
                content=f"<:check:1394240622310850580> {role.mention} に **{val}倍** のブーストを適用しました。", 
                view=None
            )
            
        select.callback = select_callback
        view.add_item(select)
        
        await interaction.response.send_message(
            f"**{val}倍** のブーストを適用するロールを選んでください。", 
            view=view, 
            ephemeral=True
        )

# --- XPブースト削除用View ---
class BoostDeleteView(ui.View):
    def __init__(self, interaction: discord.Interaction, boosts_config, original_view):
        super().__init__(timeout=None)
        self.original_view = original_view
        self.base_message = interaction.message 
        
        options = []
        for rid, multiplier in boosts_config.items():
            role = interaction.guild.get_role(int(rid))
            role_name = role.name if role else f"不明なロール (ID: {rid})"
            options.append(discord.SelectOption(
                label=f"{multiplier}倍", 
                value=rid, 
                description=f"対象: {role_name}"
            ))

        select = ui.Select(placeholder="削除するブースト設定を選択...", options=options)

        async def select_callback(inter: discord.Interaction):
            role_id_to_delete = select.values[0]
            # DBから削除
            await config_col.update_one(
                {"_id": inter.guild.id},
                {"$unset": {f"role_boosts.{role_id_to_delete}": ""}}
            )

            new_embed = await self.original_view.create_embed()
            try:
                await self.base_message.edit(embed=new_embed, view=self.original_view)
            except: pass

            await inter.response.edit_message(
                content=f"<:check:1394240622310850580> ブースト設定を削除しました。", 
                view=None
            )

        select.callback = select_callback
        self.add_item(select)

class LevelBoostView(ui.View):
    def __init__(self, bot, guild_id, author_id):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.author_id = author_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.author_id

    async def create_embed(self):
        conf = await config_col.find_one({"_id": self.guild_id})
        boosts = conf.get("role_boosts", {}) if conf else {}
        
        embed = discord.Embed(title="<:spanner:1399035839324880958> 経験値ブーストロール設定", color=0x2b2d31)
        
        if boosts:
            # 倍率順に並び替え
            sorted_boosts = sorted(boosts.items(), key=lambda x: x[1], reverse=True)
            boost_text = "\n".join([f"<@&{rid}> ： **{m}倍**" for rid, m in sorted_boosts])
        else:
            boost_text = "設定されているロールはありません。"
            
        embed.description = f"{boost_text}"
        return embed

    @ui.button(label="ロールを追加", emoji="<:buttonPlus:1444665079776808971>", style=discord.ButtonStyle.primary)
    async def add_boost(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(BoostAddModal(self))

    @ui.button(label="ロールを削除", emoji="<:buttonMinus:1444665078015066182>", style=discord.ButtonStyle.danger)
    async def remove_boost(self, interaction: discord.Interaction, button: ui.Button):
        conf = await config_col.find_one({"_id": interaction.guild.id})
        boosts = conf.get("role_boosts", {}) if conf else {}
        if not boosts:
            return await interaction.response.send_message("削除できるロールがありません。", ephemeral=True)
        await interaction.response.send_message("削除したいロールを選んでください。", view=BoostDeleteView(interaction, boosts, self), ephemeral=True)

class LeaderboardView(discord.ui.View):
    def __init__(self, bot, guild_id, pages, current_page=0):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = guild_id
        self.pages = pages
        self.current_page = current_page
        # 初期状態のボタン更新
        self.update_buttons()

    def update_buttons(self):
        """ページの状況に応じてボタンの有効・無効を切り替える"""
        total_pages = len(self.pages)
        
        # 1ページしかない場合は全ボタン無効
        if total_pages <= 1:
            for button in self.children:
                button.disabled = True
            return

        # 最初・前のページボタンの制御
        self.first_page.disabled = (self.current_page == 0)
        self.prev_page.disabled = (self.current_page == 0)
        
        # 次・最後のページボタンの制御
        self.next_page.disabled = (self.current_page == total_pages - 1)
        self.last_page.disabled = (self.current_page == total_pages - 1)

    async def update_view(self, interaction: discord.Interaction):
        # ボタンの状態を最新にしてから編集
        self.update_buttons()
        embed = await self.create_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def create_embed(self):
        # (create_embed の中身は変更なし)
        page_data = self.pages[self.current_page]
        guild = self.bot.get_guild(self.guild_id)
        
        embed = discord.Embed(
            title=f"{guild.name}のリーダーボード"
        )
        
        description = ""
        for i, data in enumerate(page_data):
            rank = (self.current_page * 10) + i + 1
            uid = int(data["_id"].split("-")[1])
            user = self.bot.get_user(uid) or await self.bot.fetch_user(uid)
            
            rank_emoji = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, "🔹")
            xp = data["xp"]
            lvl = math.floor(0.1 * math.sqrt(xp))
            
            prev_xp = int((lvl / 0.1)**2)
            next_xp = int(((lvl + 1) / 0.1)**2)
            current_progress = int(xp - prev_xp)
            needed_xp = int(next_xp - prev_xp)
            
            description += f"{rank_emoji} **{user.mention} ・レベル{lvl}・経験値:{current_progress}/{needed_xp}**\n\n"

        embed.description = description
        embed.set_thumbnail(url=guild.icon.url if guild.icon else None)
        embed.set_footer(text=f"ページ {self.current_page + 1} / {len(self.pages)}")
        return embed

    @discord.ui.button(emoji="<:prev:1401175547719192628>", style=discord.ButtonStyle.gray)
    async def first_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        await self.update_view(interaction)

    @discord.ui.button(emoji="<:leftSort:1401175053973848085>", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_view(interaction)

    @discord.ui.button(emoji="<:rightSort:1401174996574801950>", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            await self.update_view(interaction)

    @discord.ui.button(emoji="<:skip:1401175525069946920>", style=discord.ButtonStyle.gray)
    async def last_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = len(self.pages) - 1
        await self.update_view(interaction)

class ResetConfirmView(ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=30) # 30秒でタイムアウト
        self.ctx = ctx

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            return False
        return True

    @ui.button(label="はい", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        # サーバー内の全ユーザーデータを削除
        # _id が "{guild_id}-" で始まるものをすべて対象にする
        await xp_col.delete_many({"_id": {"$regex": f"^{self.ctx.guild.id}-"}})
        
        await interaction.response.edit_message(
            content=f"<:check:1394240622310850580> **{self.ctx.guild.name}**の全ユーザーのレベル・経験値をリセットしました。",
            view=None
        )

    @ui.button(label="いいえ", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.message.delete()

class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._cd_mapping = commands.CooldownMapping.from_cooldown(1, 5, commands.BucketType.member)

    # --- ヘルパー関数 ---
    def get_level(self, xp: int):
        return math.floor(0.1 * math.sqrt(xp))

    def get_xp_for_level(self, level: int):
        return int((level / 0.1)**2)

    async def get_config(self, guild_id: int):
        conf = await config_col.find_one({"_id": guild_id})
        if not conf:
            # デフォルト設定
            conf = {"_id": guild_id, "notify_channel": None, "roles": {}, "xp_rate": 1.0, "enabled": False}
        return conf

    async def is_enabled(self, ctx):
        conf = await self.get_config(ctx.guild.id)
        if not conf.get("enabled", True):
            await ctx.send("<:cross:1394240624202481705> レベル設定は無効になっています。", ephemeral=True)
            return False
        return True

    async def create_rank_card(self, member, xp, lvl, rank_num):
        """base_level_card.png を元にランクカードを生成 (座標修正済み)"""
        base_path = "assets/base_level_card.png"
        try:
            image = Image.open(base_path).convert("RGBA")
        except FileNotFoundError:
            image = Image.new("RGBA", (1000, 350), (35, 39, 42, 255))

        draw = ImageDraw.Draw(image)
        
        # --- 1. アバターの合成 ---
        async with aiohttp.ClientSession() as session:
            async with session.get(str(member.display_avatar.url)) as resp:
                if resp.status == 200:
                    avatar_bytes = await resp.read()
                    avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
                    # 白枠の内側に収まるようサイズ調整
                    avatar_img = avatar_img.resize((200, 200))
                    
                    mask = Image.new("L", (200, 200), 0)
                    mask_draw = ImageDraw.Draw(mask)
                    mask_draw.ellipse((0, 0, 200, 200), fill=255)
                    
                    # 枠のセンターに配置
                    image.paste(avatar_img, (50, 50), mask)

        # --- 2. フォント設定 ---
        font_path = "assets/Corporate-Logo-Rounded-Bold-ver3.otf"
        try:
            name_font = ImageFont.truetype(font_path, 50)      # 名前を少し大きく
            user_id_font = ImageFont.truetype(font_path, 25)   # ID
            stat_font = ImageFont.truetype(font_path, 40)      # #1 や 1
            bar_text_font = ImageFont.truetype(font_path, 25)  # 下の数値
        except OSError:
            name_font = stat_font = ImageFont.load_default()
            user_id_font = bar_text_font = ImageFont.load_default()

        # --- 3. テキスト描画 ---
        # 名前とID
        draw.text((280, 75), member.display_name, font=name_font, fill="white")
        draw.text((280, 130), f"@{member.name}", font=user_id_font, fill=(150, 150, 150))

        # 順位とレベル (ベースの「順位:」「レベル:」の文字に被らない位置)
        draw.text((745, 9), f"#{rank_num}", font=stat_font, fill="white")
        draw.text((962, 10), f"{lvl}", font=stat_font, fill="white")

        # --- 4. 経験値バーの描画 ---
        prev_lvl_xp = self.get_xp_for_level(lvl)
        next_lvl_xp = self.get_xp_for_level(lvl + 1)
        current_progress_xp = xp - prev_lvl_xp
        needed_xp_for_next = next_lvl_xp - prev_lvl_xp
        percentage = min(current_progress_xp / max(needed_xp_for_next, 1), 1.0)
        
        # バーの基本設定
        bar_x, bar_y, bar_w, bar_h = 270, 167, 621, 50 
        radius = bar_h // 2  # 半径を高さの半分に設定 (25)
        
        fill_width = int(bar_w * percentage)

        if fill_width > 0:
            # バーが短すぎても丸みが消えないように最低幅を radius * 2 に設定しつつ、
            # 描画範囲を実際の fill_width に制限するためのマスクを作成
            bar_overlay = Image.new("RGBA", (bar_w, bar_h), (0, 0, 0, 0))
            overlay_draw = ImageDraw.Draw(bar_overlay)
            
            # 1. 常に「フルサイズ」の角丸長方形を描画（左端を丸くするため）
            # ただし、右端は fill_width でカットする
            overlay_draw.rounded_rectangle([0, 0, max(fill_width, radius * 2), bar_h], 
                                           radius=radius, fill=(88, 101, 202))
            
            # 2. 進捗に合わせて右側をカットして合成
            # これにより、パーセンテージが低くても左側の丸みが維持されます
            crop_rect = (0, 0, fill_width, bar_h)
            cropped_bar = bar_overlay.crop(crop_rect)
            image.paste(cropped_bar, (bar_x, bar_y), cropped_bar)

        # バーの下のテキスト
        draw.text((275, 224), f"{percentage*100:.1f}%", font=bar_text_font, fill="white")
        xp_text = f"{int(current_progress_xp)}/{int(needed_xp_for_next)}"
        xp_text_w = draw.textlength(xp_text, font=bar_text_font)
        draw.text((920 - xp_text_w, 224), xp_text, font=bar_text_font, fill="white")

        # --- 5. 出力 ---
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        buf.seek(0)
        return buf

    # --- XP獲得イベント ---
    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or not message.guild:
            return

        # 1. 設定の取得（一度だけ呼び出すように整理）
        conf = await self.get_config(message.guild.id)
        if not conf.get("enabled", True):
            return

        # 2. クールダウン処理
        bucket = self._cd_mapping.get_bucket(message)
        retry_after = bucket.update_rate_limit()
        if retry_after:
            return

        # --- XPブースト計算の追加 ---
        # 基本倍率（デフォルト 1.0）
        final_multiplier = conf.get("xp_rate", 1.0)

        # DBからロールブースト設定を取得 {"ロールID": 倍率}
        role_boosts = conf.get("role_boosts", {})
        if role_boosts:
            user_role_ids = [str(role.id) for role in message.author.roles]
            applicable_boosts = [
                float(multiplier) 
                for rid, multiplier in role_boosts.items() 
                if rid in user_role_ids
            ]
            
            # 該当するブーストの中で最も高い倍率を適用
            if applicable_boosts:
                final_multiplier = max(final_multiplier, max(applicable_boosts))
        # ---------------------------

        # 3. 経験値の決定と更新
        xp_to_add = random.randint(15, 25) * final_multiplier
        
        guild_id = message.guild.id
        user_id = message.author.id
        key = f"{guild_id}-{user_id}"

        user_data = await xp_col.find_one_and_update(
            {"_id": key},
            {"$inc": {"xp": xp_to_add}, "$set": {"last_msg": datetime.utcnow()}},
            upsert=True,
            return_document=True
        )

        new_xp = user_data.get("xp", 0)
        old_xp = max(0, new_xp - xp_to_add)
        
        old_lvl = self.get_level(old_xp)
        new_lvl = self.get_level(new_xp)

        # 4. レベルアップ時の処理
        if old_lvl < new_lvl:
            # --- 通知処理 ---
            notify_mode = conf.get("notify_mode", "current")
            if notify_mode != "disabled":
                target_channel = message.channel
                if notify_mode in ["channel", "channel_mention"]:
                    chan_id = conf.get("notify_channel")
                    if chan_id:
                        chan = message.guild.get_channel(chan_id)
                        if chan: target_channel = chan
                
                user_display = message.author.mention if notify_mode == "channel_mention" else f"**{message.author.display_name}**"
                
                try:
                    await target_channel.send(f"🎉 {user_display} はレベル **{new_lvl}** に上がりました！")
                except discord.Forbidden:
                    pass

            # --- ロール付与・削除処理 ---
            roles_config = conf.get("roles", {})
            if roles_config:
                new_role_id = roles_config.get(str(new_lvl))
                stack_roles = conf.get("stack_roles", True)

                if not stack_roles:
                    all_set_role_ids = [int(rid) for lv, rid in roles_config.items() if int(lv) != new_lvl]
                    roles_to_remove = [message.guild.get_role(rid) for rid in all_set_role_ids if rid]
                    roles_to_remove = [r for r in roles_to_remove if r and r in message.author.roles]
                    
                    if roles_to_remove:
                        await message.author.remove_roles(*roles_to_remove)

                if new_role_id:
                    role = message.guild.get_role(int(new_role_id))
                    if role and role not in message.author.roles:
                        await message.author.add_roles(role)

    # --- コマンド群 ---
    @commands.hybrid_group(name="level", description="レベル機能の管理", aliases=["lv"])
    async def level(self, ctx):
        if ctx.invoked_subcommand is None:
            await ctx.reply("使用方法: `zp!level enable`, `zp!level edit`, `zp!level leaderboard`, `zp!level notification`, `zp!level boost-roles`, `zp!level reward-roles`, `zp!level reset`", ephemeral=True)

    @level.command(name="leaderboard", description="リーダーボードを表示します。", aliases=["l"])
    async def leaderboard(self, ctx):
        if not await self.is_enabled(ctx): return
        # 全ユーザーデータを取得して10人ずつのリストにする
        cursor = xp_col.find({"_id": {"$regex": f"^{ctx.guild.id}-"}}).sort("xp", -1)
        all_data = await cursor.to_list(length=100) # 最大100人分
        
        if not all_data:
            return await ctx.send("<:warn:1394241229176311888> まだランキングデータがありません。")

        # 10人単位のページに分割
        pages = [all_data[i:i + 10] for i in range(0, len(all_data), 10)]
        
        view = LeaderboardView(self.bot, ctx.guild.id, pages)
        embed = await view.create_embed()
        
        await ctx.send(embed=embed, view=view)

    @level.command(name="reset", description="サーバー内の全ユーザーのレベル・経験値をリセットします。", aliases=["r"])
    @commands.has_permissions(manage_guild=True)
    async def reset_all(self, ctx):
        if not await self.is_enabled(ctx): return
        view = ResetConfirmView(ctx)
        await ctx.send(
            "<:warn:1394241229176311888> このサーバー内の**全ユーザー**のレベルおよび経験値データを削除しますか？",
            view=view
        )

    @level.command(name="edit", description="ユーザーのレベル・経験値を編集します。", aliases=["e"])
    @commands.has_permissions(manage_guild=True)
    @app_commands.rename(member="メンバー", target_type="タイプ", action="操作", value="数値")
    @app_commands.describe(value="追加・削除は1以上、設定は0以上を入力してください")
    @app_commands.choices(
        target_type=[
            app_commands.Choice(name="レベル", value="level"),
            app_commands.Choice(name="経験値", value="xp"),
        ],
        action=[
            app_commands.Choice(name="追加", value="add"),
            app_commands.Choice(name="設定", value="set"),
            app_commands.Choice(name="削除", value="remove"),
        ]
    )
    async def edit_leveling(self, ctx, member: discord.Member, target_type: str, action: str, value: int):
        if not await self.is_enabled(ctx): return
        # --- 1. 入力値のバリデーション ---
        if action in ["add", "remove"] and value < 1:
            return await ctx.send("<:warn:1394241229176311888> **1以上の整数**を入力してください。", ephemeral=True)
        
        if action == "set" and value < 0:
            return await ctx.send("<:warn:1394241229176311888> **0以上の整数**を入力してください。", ephemeral=True)

        guild_id = ctx.guild.id
        key = f"{guild_id}-{member.id}"
        
        user_data = await xp_col.find_one({"_id": key})
        current_xp = user_data.get("xp", 0) if user_data else 0

        new_xp = current_xp

        if target_type == "xp":
            if action == "add":
                new_xp = current_xp + value
            elif action == "set":
                new_xp = value
            elif action == "remove":
                new_xp = current_xp - value
        
        else:
            current_lvl = self.get_level(current_xp)
            if action == "add":
                new_xp = self.get_xp_for_level(current_lvl + value)
            elif action == "set":
                new_xp = self.get_xp_for_level(value)
            elif action == "remove":
                target_lvl = max(0, current_lvl - value)
                new_xp = self.get_xp_for_level(target_lvl)

        # 最終的な結果が負にならないようにガード
        new_xp = max(0, new_xp)

        # DB更新
        await xp_col.update_one(
            {"_id": key},
            {"$set": {"xp": new_xp}},
            upsert=True
        )

        current_lvl = self.get_level(new_xp) # これで lvl の代わりに current_lvl を定義
        
        action_name = {"add": "追加", "set": "設定", "remove": "削除"}[action]
        type_name = {"level": "レベル", "xp": "経験値"}[target_type]
        
        # 現在のレベルの開始XPと、次のレベルの開始XPを取得
        start_xp = self.get_xp_for_level(current_lvl)
        next_lvl_start_xp = self.get_xp_for_level(current_lvl + 1)
        
        # 相対的なXPの計算
        relative_xp = new_xp - start_xp
        needed_xp = next_lvl_start_xp - start_xp

        xp_display = f"{relative_xp} / {needed_xp}"
        
        await ctx.send(
            f"<:check:1394240622310850580> {member.mention} の **{type_name}** を **{value}** {action_name}しました。\n"
            f"(現在のデータ: XP `{xp_display}` / レベル: `{current_lvl}`)", 
            ephemeral=True
        )

    @level.command(name="boost-roles", description="経験値ブーストロールを設定します。", aliases=["br"])
    @commands.has_permissions(manage_guild=True)
    async def setup_boosts(self, ctx):
        if not await self.is_enabled(ctx): return
        
        view = LevelBoostView(self.bot, ctx.guild.id, ctx.author.id)
        embed = await view.create_embed()
        await ctx.send(embed=embed, view=view)

    @level.command(name="reward-roles", description="報酬ロールを設定します。", aliases=["rr"])
    @commands.has_permissions(manage_guild=True)
    async def setup_roles(self, ctx):
        if not await self.is_enabled(ctx): return
        # 1. まずDBから現在の設定を取得する
        conf = await config_col.find_one({"_id": ctx.guild.id})
        # 設定がない場合はデフォルト(True: スタックする)にする
        stack_status = conf.get("stack_roles", True) if conf else True
        
        # 2. 取得した stack_status を引数に渡してViewを作成
        view = LevelRoleView(self.bot, ctx.guild.id, stack_status, ctx.author.id)
        
        # 3. Viewが編集などで使えるようにメッセージを保持しておく
        embed = await view.create_embed()
        view.message = await ctx.send(embed=embed, view=view)

    @level.command(name="notification", description="レベルアップ通知の設定を行います。", aliases=["n"])
    @commands.has_permissions(manage_guild=True)
    @app_commands.rename(mode="設定", channel="チャンネル")
    @app_commands.choices(mode=[
        app_commands.Choice(name="無効", value="disabled"),
        app_commands.Choice(name="メッセージを送信したチャンネル", value="current"),
        app_commands.Choice(name="指定したチャンネル", value="channel"),
        app_commands.Choice(name="指定したチャンネル + メンション", value="channel_mention"),
    ])
    async def notification(self, ctx, mode: str, channel: discord.TextChannel = None):
        if not await self.is_enabled(ctx): return
        # バリデーション: チャンネル指定が必要なモードでチャンネルが未選択の場合
        if mode in ["channel", "channel_mention"] and channel is None:
            return await ctx.send("<:warn:1394241229176311888> チャンネルが指定されていません。", ephemeral=True)

        update_data = {"notify_mode": mode}
        
        if channel:
            update_data["notify_channel"] = channel.id
        else:
            # モードがcurrentやdisabledの場合はチャンネル情報を消去（任意）
            update_data["notify_channel"] = None

        await config_col.update_one(
            {"_id": ctx.guild.id},
            {"$set": update_data},
            upsert=True
        )

        # 応答メッセージの作成
        mode_names = {
            "disabled": "無効",
            "current": "有効(メッセージを送信したチャンネル)",
            "channel": f" 有効({channel.mention if channel else '指定したチャンネル'})",
            "channel_mention": f"有効({channel.mention if channel else '指定したチャンネル'} + メンション )"
        }
        
        await ctx.send(f"<:check:1394240622310850580> レベルアップ通知を **{mode_names[mode]}** に設定しました。", ephemeral=True)

    @level.command(name="enable", description="レベル機能の有効/無効を切り替えます。")
    @commands.has_permissions(manage_guild=True)
    @app_commands.rename(status="有効")
    async def enable_leveling(self, ctx, status: bool):
        guild_id = ctx.guild.id
        await config_col.update_one(
            {"_id": guild_id},
            {"$set": {"enabled": status}},
            upsert=True
        )
        status_text = "**有効**" if status else "**無効**"
        await ctx.send(f"<:check:1394240622310850580> レベル設定を{status_text}にしました。", ephemeral=True)

    @commands.hybrid_command(name="rank", description="指定したメンバーまたは自分のランクカードを表示します。")
    @app_commands.rename(member="メンバー")
    async def rank(self, ctx, member: discord.Member = None):
        if not await self.is_enabled(ctx): return
        # 引数がない場合は自分を対象にする
        target = member or ctx.author
        
        # データの取得
        data = await xp_col.find_one({"_id": f"{ctx.guild.id}-{target.id}"})
        
        # XPがない、またはデータ自体が存在しない場合
        if not data or data.get("xp", 0) == 0:
            msg = f"<:warn:1394241229176311888> {target.display_name}はまだメッセージを送信していないため、ランクデータがありません。"
            if target == ctx.author:
                msg = "<:warn:1394241229176311888> まだランクデータがありません。メッセージを送信して経験値を貯めましょう！"
            
            return await ctx.send(msg, ephemeral=True)

        xp = data["xp"]
        lvl = self.get_level(xp)

        # 順位の計算（サーバー内の全ユーザーからソート）
        cursor = xp_col.find({"_id": {"$regex": f"^{ctx.guild.id}-"}}).sort("xp", -1)
        rank_num = 1
        async for entry in cursor:
            if entry["_id"] == f"{ctx.guild.id}-{target.id}":
                break
            rank_num += 1

        # 画像の生成
        async with ctx.typing():
            # 引数を target に変更して画像生成に渡す
            image_buf = await self.create_rank_card(target, xp, lvl, rank_num)
            file = discord.File(fp=image_buf, filename=f"rank_{target.id}.png")
            await ctx.send(file=file)

async def setup(bot):
    await bot.add_cog(Leveling(bot))