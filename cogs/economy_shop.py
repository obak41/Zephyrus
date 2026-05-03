import discord
from discord.ext import commands
from discord import app_commands
import random
from utils.economy_db import get_user, update_balance, users
from utils.economy_utils import format_coin, create_embed
import asyncio
from discord import ui

loss_messages = [
    ("支払い忘れていた駐車券", "駐車料金として"),
    ("身代金のメモ", "犬を取り戻すために"),
    ("手紙", "健康保険が値上がりしました。")
]

# ======================
# 💎 ショップ商品一覧
# ======================
ITEMS = {
    "coffee": {
        "name": "コーヒー",
        "description": "会社の遅刻を回避します。",
        "price": 100,
        "max": 25
    },
    "smartphone": {
        "name": "スマホ",
        "description": "銀行強盗されそうなときに連絡が来るぞ！",
        "price": 5000,
        "max": 10
    },
    "dog": {
        "name": "番犬",
        "description": "強盗犯を捕らえてくれる頼もしいパートナー。",
        "price": 1500,
        "max": 5
    },
    "clover": {
        "name": "四つ葉のクローバー",
        "description": "いいことがあるかも！",
        "price": 300,
        "max": 25
    },
    "energy": {
        "name": "エナジードリンク",
        "description": "仕事で得られるお金が増加するかも！",
        "price": 1000,
        "max": 10
    },
    "mystery_box": {
        "name": "ミステリーボックス",
        "description": "中には何が入っているかわからない…",
        "price": 1000,
        "max": 25
    },
    "lucky_box": {
        "name": "幸運のミステリーボックス",
        "description": "ミステリーボックス少し運が良いかも？",
        "price": 3000,
        "max": 25
    },
    "rod": {
        "name": "特殊な釣り竿",
        "description": "釣れるものやお金が増えるらしい。",
        "price": 300,
        "max": 25
    },
    "trophy": {
        "name": "金色のトロフィー",
        "description": "純金製のトロフィー。誇りの証。",
        "price": 10_000_000,
        "max": 1
    }
}


# ======================
# 🛒 ページネーション用View
# ======================
class ItemStoreView(discord.ui.View):
    def __init__(self, ctx, items, page=0, per_page=5):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.items = list(items.items())
        self.page = page
        self.per_page = per_page
        self.update_buttons()

    def update_buttons(self):
        # Clear previous buttons
        self.clear_items()

        # ページアイテム範囲
        start = self.page * self.per_page
        end = start + self.per_page
        total_pages = (len(self.items) + self.per_page - 1) // self.per_page

        # Embed 作成
        embed = discord.Embed(
            title="ストア",
            color=discord.Color.gold()
        )

        for key, item in self.items[start:end]:
            embed.add_field(
                name=f"{item['name']}",
                value=f"{item['description']}\n**{format_coin(item['price'])}** - 上限: `{item['max']}` 個",
                inline=False
            )

        embed.set_footer(text=f"ページ {self.page + 1}/{total_pages}")

        # ページボタン
        prev_btn = discord.ui.Button(emoji="<:leftSort:1401175053973848085>", style=discord.ButtonStyle.primary, disabled=self.page == 0)
        next_btn = discord.ui.Button(
            emoji="<:rightSort:1401174996574801950>",
            style=discord.ButtonStyle.primary,
            disabled=(self.page + 1) * self.per_page >= len(self.items)
        )

        async def prev_callback(interaction: discord.Interaction):
            if interaction.user.id != self.ctx.author.id:
                return
            self.page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embed, view=self)

        async def next_callback(interaction: discord.Interaction):
            if interaction.user.id != self.ctx.author.id:
                return
            self.page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.embed, view=self)

        prev_btn.callback = prev_callback
        next_btn.callback = next_callback

        self.add_item(prev_btn)
        self.add_item(next_btn)
        self.embed = embed

    async def start(self):
        await self.ctx.reply(embed=self.embed, view=self)


# ======================
# 💰 メインCog
# ======================
class EconomyShop(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ----------------------
    # /item store
    # ----------------------
    @commands.hybrid_group(name="item", description="アイテム関連の操作を行います。")
    async def item(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.reply("使用方法: `z!item store` `z!item buy <アイテム>` `z!item use <アイテム>`", ephemeral=True)

    @item.command(name="store", description="ショップを開きます。")
    async def item_store(self, ctx: commands.Context):
        """ストアを開く（ページ付き）"""
        view = ItemStoreView(ctx, ITEMS)
        await view.start()

    # ----------------------
    # /item buy
    # ----------------------
    @item.command(name="buy", description="アイテムを購入します。")
    @app_commands.rename(item_name="アイテム名", amount="個数")
    async def item_buy(self, ctx: commands.Context, item_name: str, amount: int = 1):
        # ============================
        # 🔍 アイテム確認
        # ============================
        item = next((v for v in ITEMS.values() if v["name"].replace(" ", "") == item_name.replace(" ", "")), None)
        if not item:
            return await ctx.reply("<:cross:1394240624202481705> アイテムが見つかりません。`/item store`で確認してください。", ephemeral=True)

        # ============================
        # ⚠️ 入力バリデーション
        # ============================
        if amount <= 0:
            return await ctx.reply("<:cross:1394240624202481705> 正の数を入力してください。", ephemeral=True)

        user = await get_user(ctx.guild.id, ctx.author.id)
        total_price = item["price"] * amount

        if user["wallet"] < total_price:
            return await ctx.reply(
                f"<:cross:1394240624202481705> 所持金が不足しています。\n"
                f"必要: {format_coin(total_price)} | 所持: {format_coin(user['wallet'])}",
                ephemeral=True
            )

        # ============================
        # 🧳 インベントリ取得・整形
        # ============================
        inventory = user.get("inventory", {})
        if isinstance(inventory, list):  # 古い形式への対応
            inventory = {name: 1 for name in inventory}

        current = inventory.get(item["name"], 0)
        if current + amount > item["max"]:
            return await ctx.reply(
                f"<:warn:1394241229176311888> `{item['name']}` は上限 `{item['max']}` 個までしか持てません。\n"
                f"現在 `{current}` 個所持しています。",
                ephemeral=True
            )

        # ============================
        # ✅ 購入処理
        # ============================
        inventory[item["name"]] = current + amount
        await users.update_one(
            {"_id": f"{ctx.guild.id}-{ctx.author.id}"},
            {
                "$set": {"inventory": inventory},
                "$inc": {"wallet": -total_price}
            }
        )

        # ============================
        # 💬 完了メッセージ
        # ============================
        await ctx.reply(
            f"<:check:1394240622310850580> **{item['name']}** を **{amount}個** 購入しました！"
        )


    # ----------------------
    # /item use
    # ----------------------
    @item.command(name="use", description="所持しているアイテムを使用します。")
    @app_commands.rename(item_name="アイテム名")
    async def item_use(self, ctx: commands.Context, item_name: str):
        user = await get_user(ctx.guild.id, ctx.author.id)
        inventory = user.get("inventory", {})
        count = inventory.get(item_name, 0)

        if count <= 0:
            return await ctx.reply(f"<:cross:1394240624202481705> `{item_name}`を持っていません。", ephemeral=True)

        # 🎁 ミステリーボックス
        if item_name == "ミステリーボックス":
            await self.open_box(ctx, user, inventory, item_name, lucky=False)

        # 🍀 幸運のミステリーボックス
        elif item_name == "幸運のミステリーボックス":
            await self.open_box(ctx, user, inventory, item_name, lucky=True)

        else:
            return await ctx.reply(f"<:warn:1394241229176311888> `{item_name}`は使用できません。", ephemeral=True)

    # ----------------------
    # 🎲 箱を開封する処理
    # ----------------------
    async def open_box(self, ctx, user, inventory, item_name, lucky=False):
        inventory[item_name] -= 1
        box_type = "幸運のミステリーボックス" if lucky else "ミステリーボックス"

        # 1️⃣ 最初のメッセージ送信
        message = await ctx.reply(f"**{box_type}**を開封しました！\n中には...")
        await asyncio.sleep(5)

        # 抽選処理
        loss_chance = 60 if lucky else 75
        roll = random.randint(1, 100)

        if roll <= loss_chance:
            # ❌ 損失パターン
            loss_amount = random.randint(500, 3000) if lucky else random.randint(100, 800)
            await update_balance(ctx.guild.id, ctx.author.id, wallet_delta=-loss_amount)
            item, msg = random.choice(loss_messages)
            await message.edit(
                content=(
                    f"**{box_type}**を開封しました！\n中には"
                    f"**{item}**が入っていました！\n"
                    f"{msg}{format_coin(loss_amount)}を支払わなければなりませんでした…"
                )
            )
        else:
            # 🎉 当たりパターン
            item_roll = random.randint(1, 100)
            if item_roll <= 80:
                reward = random.randint(4500, 5600) if lucky else random.randint(1450, 2000)
                await update_balance(ctx.guild.id, ctx.author.id, wallet_delta=reward)
                await message.edit(
                    content=(
                        f"**{box_type}**を開封しました！\n中には"
                        f"{format_coin(reward)} が入っていました！"
                    )
                )
            else:
                items = ["番犬", "四つ葉のクローバー", "エナジードリンク", "特殊な釣り竿"]
                weights = [20, 30, 30, 20]
                chosen = random.choices(items, weights=weights, k=1)[0]
                inventory[chosen] = inventory.get(chosen, 0) + 1
                await users.update_one(
                    {"_id": f"{ctx.guild.id}-{ctx.author.id}"},
                    {"$set": {"inventory": inventory}}
                )
                await message.edit(
                    content=(
                        f"**{box_type}**を開封しました！\n中には"
                        f"**{chosen}**が入っていました！"
                    )
                )

        # 🎯 最後にインベントリ更新
        await users.update_one(
            {"_id": f"{ctx.guild.id}-{ctx.author.id}"},
            {"$set": {"inventory": inventory}}
        )
        
    # ----------------------
    # /inventory
    # ----------------------
    @commands.hybrid_command(name="inventory", description="インベントリを確認します。", aliases=["inv"])
    async def item_inventory(self, ctx: commands.Context):
        user = await get_user(ctx.guild.id, ctx.author.id)
        inventory = user.get("inventory", {})

        if not inventory or all(v <= 0 for v in inventory.values()):
            return await ctx.reply("<:warn:1394241229176311888> 所持しているアイテムはありません。", ephemeral=True)

        # 有効なアイテムだけ取得
        valid_items = [(name, amount) for name, amount in inventory.items() if amount > 0]

        # 表示整形
        desc_lines = []
        for name, amount in valid_items:
            item = next((v for v in ITEMS.values() if v["name"] == name), None)
            if item:
                desc_lines.append(
                    f"**{item['name']}** - {amount}個"
                )
            else:
                desc_lines.append(f"**{name}** - {amount}個(不明なアイテム)")

        # Embed作成
        embed = create_embed(
            description="\n".join(desc_lines),
            color=discord.Color.gold()
        )
        embed.set_author(name=f"{ctx.author.display_name}のインベントリ", icon_url=ctx.author.display_avatar.url)

        await ctx.reply(embed=embed)


async def setup(bot):
    await bot.add_cog(EconomyShop(bot))
