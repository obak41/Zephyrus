import discord 
from discord.ext import commands
from discord import app_commands
import random
from utils.economy_db import get_user, update_balance, users
from utils.economy_utils import format_coin, create_embed
from discord.utils import utcnow
from discord.ui import View, button, Button
from utils.cooldowns import check_cooldown
from utils.economy_settings import get_cooldown
import time

COOLDOWN_SECONDS = 60 * 60  # 1時間

JOBS = [
    {
        "name": "サーバースタッフキャリア",
        "ranks": [
            {"rank": 1, "min": 50, "max": 50, "require": 0, "title": "見習いの清掃員"},
            {"rank": 2, "min": 75, "max": 75, "require": 3, "title": "接客業者"},
            {"rank": 3, "min": 100, "max": 100, "require": 6, "title": "データ入力事務員"},
            {"rank": 4, "min": 150, "max": 150, "require": 12, "title": "宅配便業者"},
            {"rank": 5, "min": 200, "max": 200, "require": 24, "title": "ソーシャル・メディア・インターン"},
            {"rank": 6, "min": 400, "max": 400, "require": 48, "title": "カスタマーサポート代表者"},
            {"rank": 7, "min": 450, "max": 450, "require": 96, "title": "グラフィックデザイナー"},
            {"rank": 8, "min": 500, "max": 500, "require": 120, "title": "イベントプランナー"},
            {"rank": 9, "min": 600, "max": 600, "require": 148, "title": "コンテンツ・クリエイター"},
            {"rank": 10, "min": 750, "max": 750, "require": 196, "title": "見習いのモデレーター"},
            {"rank": 11, "min": 800, "max": 800, "require": 220, "title": "コミュニティ・マネージャー"},
            {"rank": 12, "min": 900, "max": 900, "require": 260, "title": "ゲームマスター"},
            {"rank": 13, "min": 1000, "max": 1000, "require": 310, "title": "上級モデレーター"},
            {"rank": 14, "min": 1100, "max": 1100, "require": 345, "title": "見習いの開発者"},
            {"rank": 15, "min": 1300, "max": 1300, "require": 400, "title": "マーケティング専門家"},
            {"rank": 16, "min": 1500, "max": 1500, "require": 430, "title": "サーバー・アナリスト"},
            {"rank": 17, "min": 1700, "max": 1700, "require": 480, "title": "シニア開発者"},
            {"rank": 18, "min": 1900, "max": 1900, "require": 550, "title": "最高執行責任者"},
            {"rank": 19, "min": 2000, "max": 2000, "require": 1300, "title": "サーバー所有者"},
        ]
    }
]

class JobListPaginator(discord.ui.View):
    def __init__(self, make_embed_func, total_pages: int):
        super().__init__(timeout=120)
        self.make_embed_func = make_embed_func
        self.total_pages = total_pages
        self.page_index = 0

    @discord.ui.button(emoji="<:prev:1401175547719192628>", style=discord.ButtonStyle.secondary)
    async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page_index = 0
        await interaction.response.edit_message(embed=self.make_embed_func(self.page_index), view=self)

    @discord.ui.button(emoji="<:leftSort:1401175053973848085>", style=discord.ButtonStyle.primary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page_index > 0:
            self.page_index -= 1
        await interaction.response.edit_message(embed=self.make_embed_func(self.page_index), view=self)

    @discord.ui.button(emoji="<:buttonDelete:1431291664261058650>", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()

    @discord.ui.button(emoji="<:rightSort:1401174996574801950>", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page_index < self.total_pages - 1:
            self.page_index += 1
        await interaction.response.edit_message(embed=self.make_embed_func(self.page_index), view=self)

    @discord.ui.button(emoji="<:skip:1401175525069946920>", style=discord.ButtonStyle.secondary)
    async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page_index = self.total_pages - 1
        await interaction.response.edit_message(embed=self.make_embed_func(self.page_index), view=self)

class ConfirmDemotionView(View):
    def __init__(self, ctx, job_name, new_rank_info):
        super().__init__(timeout=30)
        self.ctx = ctx
        self.job_name = job_name
        self.new_rank_info = new_rank_info
        self.value = None

    @button(label="はい", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            return 

        self.value = True
        self.stop()

    @button(label="いいえ", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.ctx.author.id:
            return 

        await interaction.message.delete()
        self.stop()


    async def on_timeout(self):
        if self.ctx.interaction:
            await self.ctx.interaction.edit_original_response(view=None)


    async def apply_demotion(self):
        """降格処理"""
        new_job = {
            "name": JOBS[0]["name"],
            "rank": self.new_rank_info["rank"],
            "worked": 0,
            "title": self.new_rank_info["title"]
        }
        await users.update_one(
            {"_id": f"{self.ctx.guild.id}-{self.ctx.author.id}"},
            {"$set": {"job": new_job}}
        )

        await self.ctx.reply(
            f"降格おめでとうございます(笑)\n"
            f"あなたは今 **{self.new_rank_info['title']}** として働いています(笑)\n"
            f"新しい給料は {format_coin(self.new_rank_info['min'])} です。",
            mention_author=False
        )


class EconomyJob(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # ======================
    # 💼 /job list
    # ======================
    @commands.hybrid_group(name="job", description="仕事の確認・切り替えを行います。")
    async def job(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.reply("使用方法: `z!job list` または `z!job apply 仕事名`", ephemeral=True)

    @job.command(name="list", description="利用可能な職業を一覧表示します。")
    async def job_list(self, ctx: commands.Context):
        user = await get_user(ctx.guild.id, ctx.author.id)
        job_info = user.get("job", {"rank": 1, "worked": 0})
        current_rank = job_info.get("rank", 1)
        worked = job_info.get("worked", 0)

        job = JOBS[0]
        ranks = job["ranks"]
        per_page = 5
        total_pages = (len(ranks) + per_page - 1) // per_page

        def make_embed(page_index: int):
            start = page_index * per_page
            end = start + per_page
            page_ranks = ranks[start:end]

            embed = discord.Embed(
                title="働ける仕事",
                color=discord.Color.blurple()
            )
            for rank in page_ranks:
                title = rank["title"]
                require = rank["require"]
                salary = rank["min"]
                if rank["rank"] < current_rank:
                    icon = "<:check:1394240622310850580>"
                elif rank["rank"] == current_rank:
                    icon = "<:rightSort:1401174996574801950>"
                elif require <= worked:
                    icon = "<:check:1394240622310850580>"
                else:
                    icon = "<:cross:1394240624202481705>"

                description = {
                    "見習いの清掃員": "仮想空間を維持し、整理整頓します。",
                    "接客業者": "新メンバーを歓迎し、基本情報を提供します。",
                    "データ入力事務員": "データベースに情報を入力します。",
                    "宅配便業者": "ほかのメンバーにメッセージやアイテムを届けます。",
                    "ソーシャル・メディア・インターン": "サーバーのSNSアカウントを管理します。",
                    "カスタマーサポート代表者": "メンバーからのお問い合わせをサポートします。",
                    "グラフィックデザイナー": "サーバーのビジュアルコンテンツを作成します。",
                    "イベントプランナー": "サーバーイベントを計画・実行します。",
                    "見習いのモデレーター": "モデレーターを補佐し、秩序を維持します。",
                    "コンテンツ・クリエイター": "魅力的なコンテンツを作成します。",
                    "コミュニティ・マネージャー": "交流を促進します。",
                    "ゲームマスター": "ゲームイベントを企画・主催します。",
                    "上級モデレーター": "他のモデレーターを監督します。",
                    "見習いの開発者": "bot開発を手伝います。",
                    "マーケティング専門家": "サーバーを宣伝します。",
                    "サーバー・アナリスト": "サーバーデータを分析します。",
                    "シニア開発者": "新機能開発をリードします。",
                    "最高執行責任者": "運営全体を管理します。",
                    "サーバー所有者": "サーバー全体の責任者です。",
                }.get(title, "さまざまな仕事をこなして経験を積もう！")

                embed.add_field(
                    name=f"{icon} {title}",
                    value=f"{description}\n必要なシフト数:`{require}`\n給料:<:coin:1434901953690865816>{salary:,}コイン",
                    inline=False
                )
            embed.set_footer(text=f"ページ {page_index + 1}/{total_pages}")
            return embed

        view = JobListPaginator(make_embed, total_pages)
        await ctx.reply(embed=make_embed(0), view=view)

    # ======================
    # 📝 /job apply
    # ======================
    @job.command(name="apply", description="職業に応募します。")
    @app_commands.rename(job_name="職業名")
    async def job_apply(self, ctx: commands.Context, job_name: str):
        job = JOBS[0]  # 今のところ1キャリアライン固定
        rank_info = next((r for r in job["ranks"] if r["title"] == job_name), None)
        if not rank_info:
            return await ctx.reply("<:cross:1394240624202481705> 仕事が見つかりません。`/job list`で確認してください。", ephemeral=True)

        user = await get_user(ctx.guild.id, ctx.author.id)
        user_job = user.get("job", {"rank": 1, "worked": 0})
        worked = user_job.get("worked", 0)
        current_rank = user_job.get("rank", 1)

        # 🔹勤務数が足りない
        if worked < rank_info["require"]:
            return await ctx.reply(
                f"<:warn:1394241229176311888> **{rank_info['title']}** として働くには少なくとも **{rank_info['require']}回** 働く必要があります。\n"
                f"あなたは現在 **{worked}回** しか働いていません。",
                ephemeral=True
            )

        # 🔹昇格
        if rank_info["rank"] > current_rank:
            new_job = {
                "name": job["name"],
                "rank": rank_info["rank"],
                "worked": worked,
                "title": rank_info["title"]
            }
            await users.update_one(
                {"_id": f"{ctx.guild.id}-{ctx.author.id}"},
                {"$set": {"job": new_job}}
            )

            return await ctx.reply(
                f"昇格おめでとうございます！ あなたは今 **{rank_info['title']}** として働いています。\n"
                f"新しい給料は {format_coin(rank_info['min'])} です。",
                mention_author=False
            )

        # 🔹降格確認
        if rank_info["rank"] < current_rank:
            view = ConfirmDemotionView(ctx, job_name, rank_info)
            await ctx.reply(
                f"<:warn:1394241229176311888> **{rank_info['title']}** は現在の仕事より給料が低いようです。転職しますか？",
                view=view,
                mention_author=False
            )
            await view.wait()

            if view.value:
                await view.apply_demotion()
            else:
                return

        # 🔹すでに同じ職業
        if rank_info["rank"] == current_rank:
            return await ctx.reply(f"<:warn:1394241229176311888> すでに **{rank_info['title']}** として働いています。", ephemeral=True)

    # ======================
    # 💰 /work
    # ======================
    @commands.hybrid_command(name="work", description="働いて給料を稼ぎます。")
    async def work(self, ctx: commands.Context):

        if ctx.interaction and ctx.interaction.response.is_done():
            return

        if ctx.interaction and ctx.interaction.response.is_done():
            return

        guild_id = ctx.guild.id
        user_id = ctx.author.id

        user = await get_user(guild_id, user_id)
        job = user.get("job")

        if "job" not in user:
            first_rank = JOBS[0]["ranks"][0]
            user["job"] = {
                "name": JOBS[0]["name"],
                "rank": first_rank["rank"],
                "worked": 0,
                "title": first_rank["title"]
            }

            await users.update_one(
                {"_id": f"{guild_id}-{user_id}"},
                {"$set": {"job": user["job"]}}
            )

        job_data = next(
            (j for j in JOBS if j["name"] == user["job"]["name"]),
            None
        )
        if not job_data:
            return await ctx.reply("<:cross:1394240624202481705> 職業データが見つかりません。")

        rank_info = next(
            (r for r in job_data["ranks"] if r["rank"] == user["job"]["rank"]),
            None
        )
        if not rank_info:
            return await ctx.reply("<:cross:1394240624202481705> ランクデータが見つかりません。")

        ok, remain = await check_cooldown(guild_id, user_id, "work")
        if not ok:
            until = int(time.time() + remain)
            await ctx.reply(
                f"<:warn:1394241229176311888> クールダウン中です。<t:{until}:R>に再度実行してください。"
            )
            return

        # ======================
        # 🎲 勤務イベント抽選
        # ======================
        roll = random.randint(1, 100)
        multiplier = 1.0
        status_message = ""
        coffee_used = False

        # ☕ 遅刻（30%）
        if roll <= 30:
            inventory = user.get("inventory", {})
            coffee_count = inventory.get("コーヒー", 0)

            if coffee_count > 0:
                # コーヒー使用して遅刻回避
                inventory["コーヒー"] -= 1
                coffee_used = True
                await users.update_one(
                    {"_id": f"{ctx.guild.id}-{ctx.author.id}"},
                    {"$set": {"inventory": inventory}}
                )
                remain = coffee_count - 1
                status_message = f"コーヒーのおかげで寝坊せずに出勤できました！残りは{remain}個です。"
            else:
                # 遅刻して給料半減
                multiplier = 0.5
                status_message = (
                    "が、\n遅刻したため給料が半分になりました...\n"
                    "💡 `コーヒー`を買っておくと遅刻を防げます！"
                )

        # 💨 早出（15%）
        elif roll >= 86:
            multiplier = 2.0
            status_message = "\nさらに、いつもより早めに出勤したため、給料が2倍になりました！"

        base = random.randint(rank_info["min"], rank_info["max"])
        reward = int(base * multiplier)

        # ======================
        # 💾 データ更新
        # ======================
        await update_balance(ctx.guild.id, ctx.author.id, wallet_delta=reward)
        await users.update_one(
            {"_id": f"{guild_id}-{user_id}"},
            {"$inc": {"job.worked": 1, "total_salary": reward}},
            upsert=True
        )

        # ======================
        # 💬 メッセージ送信
        # ======================
        coffee_note = "（☕ コーヒーを使用）" if coffee_used else ""
        await ctx.reply(
            f"{rank_info['title']}として働き、{format_coin(reward)}を受け取りました！{coffee_note}\n{status_message}"
        )

        # ======================
        # 🎖️ 昇進チェック
        # ======================
        next_rank = next((r for r in job_data["ranks"] if r["rank"] == user["job"]["rank"] + 1), None)
        if next_rank and user["job"]["worked"] >= next_rank["require"]:
            await ctx.reply(
                f"🎉 **昇進チャンス！**\n"
                f"次の役職「{next_rank['title']}」に応募できます。\n"
                f"`/job apply {next_rank['title']}` で昇進してください！"
            )


async def setup(bot):
    await bot.add_cog(EconomyJob(bot))
