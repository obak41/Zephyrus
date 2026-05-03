import random
import discord
from discord.ext import commands
from discord import app_commands
import asyncio
from utils.economy_settings import get_cooldown

from utils.economy_db import (
    get_user,
    update_balance,
    log_transaction,
    update_inventory,
    users
)
from utils.economy_utils import (
    format_coin,
    normalize_inventory,
    inc_stat
)

from utils.economy_bank import (
    get_bank_last_robbed,
    set_bank_last_robbed
)

from utils.cooldowns import check_cooldown
import time

def cooldown_message(until_unix: int) -> str:
    return f"<:warn:1394241229176311888> クールダウン中です。<t:{until_unix}:R>に再度実行してください。"

success_crime_message = [
    "スリに成功し、{amount}を獲得しました！",
    "忍者のスキルを駆使して、宝石店から{amount}を盗みました！",
    "銀行をハッキングし、{amount}をあなたの口座に送金しました！",
    "カジノ強盗に成功し、{amount}をチップとして獲得しました！",
    "偽のアートで美術館の全員を騙し、絵を{amount}で売りました！",
    "知名度の高いオークションに潜入し、{amount}相当の貴重なアイテムを盗みました！",
    "脅迫に成功し、有名人から{amount}を騙し取りました！",
    "見事な説得により、地元企業の経営者は保護費として{amount}を支払うことになりました！",
    "違法な商品の密輸に成功し、{amount}を獲得しました！",
    "真夜中の列車強盗は無事に終わり、{amount}を獲得しました！",
    "大胆な美術館強盗からの脱出はみんなを驚かせ{amount}を獲得しました！",
    "地下の格闘倶楽部に優勝し、{amount}を獲得しました！",
    "サイバー攻撃に成功し、貴重なデータを盗んで{amount}で売りました！",
    "秘密の情報提供者が高額な貨物を密輸し、{amount}の利益をもたらしました！",
    "素早い反射神経で警察の追跡から逃れ、{amount}を獲得しました！",
    "豪邸での強盗に成功し、{amount}相当の貴重な工芸品を盗みました！",
    "違法なレースは順調に進み、ギャンブルのスキルによって{amount}を獲得しました！",
    "あなたはレアなグッズを偽造し、{amount}の利益で売りました！",
    "見事な説得で暴力団に保護費を支払うよう説得し、{amount}を獲得しました！",
    "地下鉄でのスリ作戦に成功し、{amount}を獲得しました！"
]

fail_crime_message = [
    "スリをしていたのが警察に気づかれ、{amount}を失いました...",
    "銀行強盗に失敗し、{amount}を失いました...",
    "あなたのハッキングスキルが足りず、{amount}を失いました...",
    "カジノのセキュリティが厳しすぎて、{amount}を失いました...",
    "美術館で偽のアートがバレて、{amount}の罰金を支払いました...",
    "オークションの警備員に捕まり、{amount}相当の盗品を失いました...",
    "脅迫に失敗し、{amount}の口止め料を支払いました...",
    "地元の経営者にハッタリをかまされ、{amount}を失いました...",
    "警察官があなたの違法商品を取り締まり、{amount}を失いました...",
    "真夜中の列車強盗を阻止され、{amount}の弁護士費用を支払いました...",
    "強盗の最中に美術館の警備員に見つかり、{amount}の罰金を支払いました...",
    "地下の格闘倶楽部で負け、{amount}の賭け金を失いました...",
    "サイバー攻撃を突き止められ、{amount}を失い、法的問題に発展しました...",
    "高価な貨物が盗品であることが判明し、{amount}を失いました...",
    "警察の検問で逃走を阻まれ、{amount}を失いました...",
    "大豪邸の強盗に失敗し、{amount}相当の盗品を失いました...",
    "違法なレースで事故が発生し、{amount}の修理費を負担することになりました...",
    "偽物のグッズが見つかり、{amount}を失い、訴訟に発展しました...",
    "暴力団の抗争に巻き込まれ、{amount}を失いました...",
    "地下鉄でのスリが潜入捜査官に見つかり、{amount}を失いました...",
]

success_beg_message = [
    "あなたは街角でひたすら乞食をし、{amount}を獲得しました！",
    "通行人はあなたに同情してくれて、乞食をして{amount}を手に入れました！",
    "気前のいい見知らぬ人が{amount}を落としました！",
    "雨にもかかわらず、あなたは同情的な見物人から{amount}を獲得しました！",
    "あなたのかわいそうな話が親切な人の心に触れ、{amount}を手渡しました！",
    "カフェの外で乞食をして、{amount}を集めました！",
    "あなたは裕福そうな人に声をかけ、{amount}をおねだりしました！",
    "公園の近くで乞食をして、{amount}を獲得しました！",
    "町の広場で必死に訴えた結果、{amount}を獲得しました！",
    "同情してくれた店主が、あなたに{amount}をくれました！",
    "閑散とした日にもかかわらず、あなたの粘り強い乞食によって{amount}を獲得しました！",
    "心優しい見知らぬ人が、あなたに{amount}を手渡しました！",
    "バス停での乞食は報われ、あなたは{amount}を獲得しました！",
    "駅の近くで乞食をして、{amount}を獲得しました！",
    "最初は半信半疑だったのにもかかわらず、あなたの心にこもった嘆願によって{amount}を手に入れることができました！",
    "観光客があなたに同情し、あなたの乞食努力で{amount}を獲得しました！",
    "図書館の外で物乞食をして、{amount}を獲得しました！",
    "あなたの独創的なサインは多くの人の注目を集め、{amount}を獲得しました！",
    "地元の音楽家があなたの話に感動し、{amount}を貰いました！",
]

neutral_beg_message = [
    "せっかく努力したのに通行人はあなたの願いを無視し、何も得られませんでした。",
    "人々は一目も見ずに通り過ぎていきました。",
    "市場の近くで乞食をしましたが、気づいてもらえず、何ももらえませんでした。",
    "残念ながら、あなたの話は誰魅了せず、寄付も得られませんでした。",
    "あなたが最善を尽くしたにもかかわらず、町の広場の観衆は無関心なままで、あなたは何も得られませんでした。",
    "バス停の通勤客は見向きもせず、あなたの願いは何も届きませんでした。",
    "駅にいた旅人たちはあなたの嘆願を無視し、あなたは手ぶらで帰ることになりました。",
    "図書館の近くで独創的なサインをしましたが、まったく同情されず、何も得られませんでした。",
    "あなたの誠意とは裏腹に、公園では誰からも何の支援も得られず、手ぶらで帰ることになりました。",
    "パン屋の常連客は無反応で、あなたの願いは何の成果も得られませんでした。",
]

fail_beg_mesasge = [
    "市場の近くで物乞いをしていると、誰かがあなたのコップから小銭を奪っていき、{amount}を失いました...",
    "残念なことに、物乞い中にスリに狙われ、{amount}を失いました...",
    "あなたの努力が報われたにもかかわらず、いたずらっ子があなたのコップからお金を盗んだため、{amount}の損失が発生しました...",
    "バス停で物乞いをしていた時、強い突風にあおられてお金が飛んでしまい、{amount}を失いました...",
    "通りすがりの人が寄付するふりをして、{amount}を盗みました...",
    "あなたの独創的な物乞いがトラブルメーカーに目を付けられ、隠し持っていた{amount}を盗まれました...",
    "公園でペットの飼い犬が誤ってコップを倒してしまい、{amount}を失いました...",
    "物乞いの仲間に説得され、{amount}を失うことになりました...",
    "残念なことに、いたずらで水風船を投げられ、{amount}を失いました...",
    "図書館の外で物乞いをしていた時、誰かがあなたに体当たりし、あなたは転倒して{amount}を失いました...",
]

class BankRobView(discord.ui.View):
    def __init__(self, cog, guild_id, bank_id, author_id):
        super().__init__(timeout=None)
        self.cog = cog
        self.guild_id = guild_id
        self.bank_id = bank_id
        self.author_id = author_id

    @discord.ui.button(label="強盗に参加", style=discord.ButtonStyle.success)
    async def join(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.bank_id:
            await interaction.response.send_message(
                "<:warn:1394241229176311888> ターゲットは銀行強盗に参加できません。",
                ephemeral=True
            )
            return
        data = self.cog.active_bank_robberies[self.guild_id]

        if interaction.user.id in data["participants"]:
            await interaction.response.send_message(
                "すでに参加しています。", ephemeral=True
            )
            return

        user_data = await get_user(interaction.guild.id, interaction.user.id)
        bank_msg = ""
        if user_data["wallet"] < 3000 and user_data["bank"] < 3000:
            await interaction.response.send_message(f"<:warn:1394241229176311888> 強盗に参加するには{format_coin(3000)}を預金する必要があります。")
            return
        elif user_data["bank"] < 3000:
            await update_balance(interaction.guild.id, interaction.user.id, wallet_delta=-3000)
            await update_balance(interaction.guild.id, interaction.user.id, bank_delta=3000)
            bank_msg = "\n-# 強盗に参加するために口座に3000コインを預金しました。" 

        data["participants"].add(interaction.user.id)
        await interaction.response.send_message(
            f"強盗に参加しました！{bank_msg}", ephemeral=True
        )

        # メッセージ編集（参加人数更新）
        embed = data["message"].embeds[0]
        embed.set_footer(text=f"参加者: {len(data['participants'])}人")
        await data["message"].edit(embed=embed)

    @discord.ui.button(label="警察に通報", style=discord.ButtonStyle.danger)
    async def report(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.bank_id:
            await interaction.response.send_message(
                "<:warn:1394241229176311888> ターゲット以外は警察に通報できません。",
                ephemeral=True
            )
            return

        data = self.cog.active_bank_robberies[self.guild_id]

        if data["reported"]:
            await interaction.response.send_message(
                "すでに通報しています。", ephemeral=True
            )
            return

        data["reported"] = True

        await interaction.response.send_message(
            "警察に通報しました！強盗は失敗するでしょう(笑)",
            ephemeral=True
        )


class EconomyCrime(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_bank_robberies = {}
    # --------------------
    # /crime
    # --------------------
    @commands.hybrid_command(name="crime", description="犯罪を犯します。")
    async def crime(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        user_id = ctx.author.id
        user = await get_user(guild_id, user_id)
        inv_user = normalize_inventory(user)
        extra_msg = ""
        clover_msg = ""

        if user["wallet"] < 1000:
            await ctx.reply(f"<:warn:1394241229176311888> 犯罪を犯すには{format_coin(1000)}が必要です。")
            return

        ok, remain = await check_cooldown(guild_id, user_id, "crime")
        if not ok:
            until = int(time.time() + remain)
            await ctx.reply(cooldown_message(until))
            return

        has_clover = inv_user.get("四つ葉のクローバー", 0) > 0
        success_rate = 0.8 if has_clover else 0.6
        success = random.random() < success_rate

        if has_clover:
            await update_inventory(guild_id, user_id, "四つ葉のクローバー", -1)

            remain = inv_user.get("四つ葉のクローバー", 0) - 1
            clover_msg = f"\n四つ葉のクローバーを消費しました。残りは{remain}個です。"

        amount = random.randint(500, 1500)

        await inc_stat(ctx.guild.id, ctx.author.id, "police")
        if success:
            await update_balance(guild_id, user_id, wallet_delta=amount)
            msg = random.choice(success_crime_message).format(
                amount=format_coin(amount)
            )
            await log_transaction(guild_id, user_id, user_id, amount, "犯罪成功")
        else:
            await update_balance(guild_id, user_id, wallet_delta=-amount)
            msg = random.choice(fail_crime_message).format(
                amount=format_coin(amount)
            )
            await log_transaction(guild_id, user_id, user_id, -amount, "犯罪失敗")
        extra_msg = ""
        if success:
            if random.randint(1, 100) == 1:
                collections = user.get("collections")

                # 念のため list → dict 修正
                if not isinstance(collections, dict):
                    collections = {}
                    await users.update_one(
                        {"_id": f"{ctx.guild.id}-{ctx.author.id}"},
                        {"$set": {"collections": collections}}
                    )

                # まだ持っていない場合のみ付与
                if "💎 - ダイヤモンド" not in collections:
                    await users.update_one(
                        {"_id": f"{ctx.guild.id}-{ctx.author.id}"},
                        {"$set": {"collections.💎 - ダイヤモンド": 1}}
                    )
                    extra_msg = '\n🎉 さらに、収集品 **"💎 - ダイヤモンド"** を獲得しました！'
                else:
                    extra_msg = ""  # すでに持っている場合は何も出さない

        await ctx.reply(f"{msg}{clover_msg}{extra_msg}")

    # --------------------
    # /beg
    # --------------------
    @commands.hybrid_command(name="beg", description="乞食をします。")
    async def beg(self, ctx: commands.Context):
        guild_id = ctx.guild.id
        user_id = ctx.author.id
        user = await get_user(guild_id, user_id)
        inv_user = normalize_inventory(user)
        extra_msg = ""
        clover_msg = ""

        ok, remain = await check_cooldown(guild_id, user_id, "beg")
        if not ok:
            until = int(time.time() + remain)
            await ctx.reply(cooldown_message(until))
            return

        has_clover = (await get_user(guild_id, user_id)) \
            .get("inventory", {}).get("四つ葉のクローバー", 0) > 0

        success = False
        extra_msg = ""
        roll = random.random()
        if roll < (0.9 if has_clover else 0.6):
            amount = random.randint(40, 150)
            await update_balance(guild_id, user_id, wallet_delta=amount)
            msg = random.choice(success_beg_message).format(
                amount=format_coin(amount)
            )
            await log_transaction(guild_id, user_id, user_id, amount, "乞食成功")
            success = True
        elif roll < (1.0 if has_clover else 0.9):
            msg = random.choice(neutral_beg_message)
        else:
            amount = random.randint(40, 150)
            await update_balance(guild_id, user_id, wallet_delta=-amount)
            msg = random.choice(fail_beg_mesasge).format(
                amount=format_coin(amount)
            )
            await log_transaction(guild_id, user_id, user_id, -amount, "乞食失敗")

        if has_clover:
            await update_inventory(guild_id, user_id, "四つ葉のクローバー", -1)

            remain = inv_user.get("四つ葉のクローバー", 0) - 1
            clover_msg = f"\n四つ葉のクローバーを消費しました。残りは{remain}個です。"

        if success == True:
            if random.randint(1, 100) == 1:
                collections = user.get("collections")

                # 念のため list → dict 修正
                if not isinstance(collections, dict):
                    collections = {}
                    await users.update_one(
                        {"_id": f"{ctx.guild.id}-{ctx.author.id}"},
                        {"$set": {"collections": collections}}
                    )

                # まだ持っていない場合のみ付与
                if "👞 - 古びた革靴" not in collections:
                    await users.update_one(
                        {"_id": f"{ctx.guild.id}-{ctx.author.id}"},
                        {"$set": {"collections.👞 - 古びた革靴": 1}}
                    )
                    extra_msg = '\n🎉 さらに、収集品 **"👞 - 古びた革靴"** を獲得しました！'
                else:
                    extra_msg = ""  # すでに持っている場合は何も出さない

        await inc_stat(ctx.guild.id, ctx.author.id, "beg")
        await ctx.reply(f"{msg}{clover_msg}{extra_msg}")


    # --------------------
    # /rob player
    # --------------------
    @commands.hybrid_group(name="rob", description="プレイヤーや銀行を強盗する")
    async def rob(self, ctx: commands.Context):
        pass
    @rob.command(name="player", description="プレイヤーの財布からお金を盗みます。")
    @app_commands.rename(target="ターゲット")
    async def rob_player(self, ctx: commands.Context, target: discord.Member):
        if target.bot:
            await ctx.reply(
                "<:cross:1394240624202481705>botの金は盗めません。",
                ephemeral=True
            )
            return
        if target.id == ctx.author.id:
            await ctx.reply(
                "<:cross:1394240624202481705>自分自身を強盗できません。",
                ephemeral=True
            )
            return

        guild_id = ctx.guild.id
        robber = ctx.author.id
        victim = target.id
        robber_data = await get_user(guild_id, robber)
        victim_data = await get_user(guild_id, victim)
        inv_robber = normalize_inventory(robber_data)
        inv_victim = normalize_inventory(victim_data)

        if robber_data["wallet"] < 3000:
            await ctx.reply(f"<:warn:1394241229176311888> 強盗するには{format_coin(3000)}が必要です。")
            return

        ok, remain = await check_cooldown(guild_id, robber, "rob")
        if not ok:
            until = int(time.time() + remain)
            await ctx.reply(cooldown_message(until))
            return

        if victim_data["wallet"] < 100:
            await ctx.reply(f"{target.mention}のお金を盗もうとしましたが、貧乏だったようです...")
            return

        has_clover = inv_robber.get("四つ葉のクローバー", 0) > 0
        victim_has_dog = inv_victim.get("番犬", 0) > 0

        if victim_has_dog:
            success_rate = 0.4
        else:
            success_rate = 0.8 if has_clover else 0.7

        success = random.random() < success_rate
        clover_msg = ""

        # 四つ葉は使ったら必ず消費
        if has_clover:
            await update_inventory(guild_id, robber, "四つ葉のクローバー", -1)
            remain = inv_robber.get("四つ葉のクローバー", 0)
            clover_msg = f"\n四つ葉のクローバーを消費しました。残りは{remain}個です。"

        if success:
            if victim_has_dog:
                watchdog_msg = f"{target.mention}の番犬をかいくぐって"
            else:
                watchdog_msg = ""
            stolen = int(victim_data["wallet"] * 0.2)
            await update_balance(guild_id, robber, wallet_delta=stolen)
            await update_balance(guild_id, victim, wallet_delta=-stolen)
            msg = f"{watchdog_msg}{target.mention}を襲い、{format_coin(stolen)}を奪いました！{clover_msg}"
            await log_transaction(guild_id, robber, robber, stolen, "強盗成功")
            await log_transaction(guild_id, robber, victim, -stolen, "強盗被害による損失")
            await inc_stat(ctx.guild.id, ctx.author.id, "crime")
        else:
            if victim_has_dog:
                watchdog_msg = f"{target.mention}の番犬に捕まりました。"
            else:
                watchdog_msg = f"本人に気づかれ、取り押さえられました。"
            fine = int(robber_data["wallet"] * 0.1)
            await update_balance(guild_id, robber, wallet_delta=-fine)
            await update_balance(guild_id, victim, wallet_delta=fine)
            msg = f"{target.mention}を襲いましたが、{watchdog_msg}{ctx.author.mention}は罰金として{format_coin(fine)}を支払いました。{clover_msg}"
            await log_transaction(guild_id, robber, robber, -fine, "強盗失敗")
            await log_transaction(guild_id, robber, victim, fine, "強盗による罰金")
            if victim_has_dog:
                await update_inventory(guild_id, victim, "番犬", -1)

        if has_clover:
            await update_inventory(guild_id, robber, "四つ葉のクローバー", -1)

            remain = inv_robber.get("四つ葉のクローバー", 0) - 1
            clover_msg = f"\n四つ葉のクローバーを消費しました。残りは{remain}個です。"

        await ctx.reply(msg)

    # --------------------
    # /rob bank
    # --------------------
    @rob.command(name="bank", description="銀行強盗をします。")
    @app_commands.rename(target="ターゲット")
    async def rob_bank(self, ctx: commands.Context, target: discord.Member):
        guild_id = ctx.guild.id
        bank_owner_id = target.id
        now = int(time.time())
        start_time = now + 60

        # --------------------
        # クールダウン（銀行単位）
        # --------------------
        last = await get_bank_last_robbed(guild_id, bank_owner_id)
        BANK_COOLDOWN = 12 * 60 * 60  # 12時間
        if last and now - last < BANK_COOLDOWN:
            remain = BANK_COOLDOWN - (now - last)
            until = now + remain
            await ctx.reply(
                f"<:warn:1394241229176311888>指定したターゲットの銀行は強盗されたばかりです。<t:{until}:R> に再度強盗できます。"
            )
            return

        robber_data = await get_user(guild_id, ctx.author.id)
        if robber_data["bank"] < 10000:
            await ctx.reply(
                f"<:warn:1394241229176311888>銀行強盗を始めるには{format_coin(10000)}預金する必要があります。"
            )
            return

        target_data = await get_user(guild_id, bank_owner_id)
        if target_data["bank"] < 10000:
            await ctx.reply(f"<:warn:1394241229176311888>銀行強盗を始めるにはターゲットの銀行に{format_coin(10000)}預金されている必要があります。")
            return

        ok, remain = await check_cooldown(guild_id, ctx.author.id, "bankrob")
        if not ok:
            until = int(time.time() + remain)
            await ctx.reply(cooldown_message(until))
            return

        # --------------------
        # 募集開始（1枚目）
        # --------------------
        embed = discord.Embed(
            title=f"{ctx.author.display_name}が銀行強盗を始めました！",
            description=(
                f"{target.mention}の銀行に押し入ろうとしています！\n\n"
                f"「強盗に参加」ボタンを押して強盗に参加してください！\n"
                f"**<t:{start_time}:R> に強盗が始まります！**\n\n"
                f"ターゲットは強盗が始まる前に「警察に通報」を押してください。"
            ),
            color=discord.Color.purple()
        )
        embed.set_footer(text="参加者: 1人")

        view = BankRobView(self, guild_id, bank_owner_id, ctx.author.id)
        msg = await ctx.reply(embed=embed, view=view)

        self.active_bank_robberies[guild_id] = {
            "message": msg,
            "participants": {ctx.author.id},
            "reported": False,
            "bank_owner": bank_owner_id,
            "started_at": now
        }

        # --------------------
        # 募集時間（60秒）
        # --------------------
        await asyncio.sleep(60)

        data = self.active_bank_robberies.get(guild_id)
        if not data:
            return

        # --------------------
        # 募集締切（3枚目）
        # --------------------
        embed.title = f"{ctx.author.display_name}が銀行強盗を始めました！"
        embed.description = (
            f"参加者: {len(data['participants'])}人\n\n"
            f"結果は数秒後に出ます。"
        )
        embed.set_footer(text="")
        await msg.edit(embed=embed, view=None)

        await asyncio.sleep(5)

        participants = list(data["participants"])
        count = len(participants)
        target_data = await get_user(guild_id, bank_owner_id)

        # ====================
        # ❌ 失敗（人数不足）
        # ====================
        if count <= 1:
            embed.title = f"{ctx.author.display_name}の銀行強盗は失敗しました！"
            embed.description = (
                f"彼らは{target.mention}の銀行に押し入ろうとしましたが、誰も強盗に参加しませんでした！"
            )
            embed.color = discord.Color.red()
            embed.set_footer(text="")

            # クールダウンだけは付与
            await set_bank_last_robbed(guild_id, bank_owner_id, now)

            await msg.edit(embed=embed)
            del self.active_bank_robberies[guild_id]
            return

        # ====================
        # 🚨 失敗（警察通報）
        # ====================
        if data["reported"]:
            total_loss = 0
            lines = []

            for uid in participants:
                user = await get_user(guild_id, uid)
                fine = int(user["bank"] * 0.1)

                await update_balance(guild_id, uid, bank_delta=-fine)
                await update_balance(guild_id, bank_owner_id, bank_delta=fine)
                await log_transaction(guild_id, uid, uid, -fine, "銀行強盗失敗")
                await log_transaction(guild_id, bank_owner_id, bank_owner_id, fine, "銀行強盗による罰金")

                total_loss += fine
                lines.append(f"<@{uid}>: {format_coin(fine)}")
            embed.title = f"{ctx.author.display_name}の銀行強盗は失敗しました！"
            embed.description = (
                f"{target.mention}は警察に通報することができました！\n"
                f"{count}人の泥棒が逮捕され、"
                f"それぞれ銀行残高の10%を賠償金として支払いました！\n"
                f"総額は{format_coin(total_loss)}でした！"
                + "\n".join(lines)
            )
            embed.color = discord.Color.red()

        # ====================
        # 💰 成功
        # ====================
        else:
            # 人数 × 5%（最大100%）
            steal_rate = 1.0 if count >= 20 else count * 0.05
            total_stolen = int(target_data["bank"] * steal_rate)
            per_user = total_stolen // count

            await update_balance(
                guild_id,
                bank_owner_id,
                bank_delta=-total_stolen
            )
            await log_transaction(guild_id, bank_owner_id, bank_owner_id, -total_stolen, "銀行強盗による損失")

            for uid in participants:
                await update_balance(
                    guild_id,
                    uid,
                    bank_delta=per_user
                )
                await log_transaction(guild_id, uid, bank_owner_id, per_user, "銀行強盗成功")

            embed.title = f"{ctx.author.display_name}の銀行強盗は成功しました！"
            embed.description = (
                f"彼らは{target.mention}の銀行に押し入り、{format_coin(total_stolen)}を盗みました！\n"
                f"{count}人が強盗に加わり、それぞれ{format_coin(per_user)}を奪い取りました！"
            )
            embed.color = discord.Color.green()

            await set_bank_last_robbed(guild_id, bank_owner_id, now)

        await msg.edit(embed=embed)
        del self.active_bank_robberies[guild_id]

async def setup(bot):
    await bot.add_cog(EconomyCrime(bot))
