from __future__ import annotations

from typing import List

import discord
from discord import app_commands
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
import io
import datetime
from datetime import timezone, timedelta
import os
from dotenv import load_dotenv

ticket_logs: dict[int, list[str]] = {}

JST = timezone(timedelta(hours=9))

# ========== MongoDB 設定 ==========
load_dotenv()

client = AsyncIOMotorClient(os.getenv("MONGO_URI"))
db = client["tickettools"]
mentions_col = db["mentions"]
categories_col = db["channel_categories"]

# ========== DB操作 ==========
async def _get_mentions_doc(guild_id: int):
    doc = await mentions_col.find_one({"guild_id": guild_id})
    if not doc:
        doc = {"guild_id": guild_id, "mention_roles": []}
        await mentions_col.insert_one(doc)
    return doc

async def load_role_ids(guild_id: int) -> List[int]:
    doc = await _get_mentions_doc(guild_id)
    return list(doc["mention_roles"])

async def save_role_ids(guild_id: int, role_ids: List[int]) -> None:
    await mentions_col.update_one(
        {"guild_id": guild_id},
        {"$set": {"mention_roles": list(dict.fromkeys(role_ids))}},
        upsert=True,
    )

async def _get_ticket_doc(guild_id: int):
    doc = await categories_col.find_one({"guild_id": guild_id})
    if not doc:
        doc = {"guild_id": guild_id, "ticket_category": None}
        await categories_col.insert_one(doc)
    return doc

async def save_ticket_category(guild_id: int, category_id: int | None):
    await categories_col.update_one(
        {"guild_id": guild_id},
        {"$set": {"ticket_category": category_id}},
        upsert=True,
    )

async def load_ticket_category(guild_id: int) -> int | None:
    doc = await _get_ticket_doc(guild_id)
    return doc.get("ticket_category")

# ========== Embed ビルダー ==========
def build_panel_embed(guild: discord.Guild, role_ids: List[int]) -> discord.Embed:
    roles_text = "なし"
    if role_ids:
        parts = []
        for rid in role_ids:
            role = guild.get_role(rid)
            parts.append(role.mention if role else f"`{rid}` *(不明)*")
        roles_text = "\n".join(parts)

    emb = discord.Embed(
        title="<:spanner:1399035839324880958>チケットツール メンション設定",
        color=discord.Color.blurple(),
    )
    emb.add_field(name="通知ロール", value=roles_text, inline=False)
    return emb

# --- チケット関連のビュー ---
class TicketOpenView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # 永続化

    @discord.ui.button(
        label="チケットを開く",
        style=discord.ButtonStyle.primary,
        custom_id="tickettool:open"
    )
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        user = interaction.user
        if not guild:
            await interaction.response.send_message("ギルド内でのみ使用できます。", ephemeral=True)
            return

        doc = await mentions_col.find_one({"guild_id": interaction.guild.id})
        mention_roles = doc.get("mention_roles", []) if doc else []
        mentions_text = " ".join([f"<@&{rid}>" for rid in mention_roles])

        # チケット番号（既存チャンネル名の先頭 "チケット" を数える）
        ticket_number = len([c for c in guild.text_channels if c.name.startswith("チケット")]) + 1
        channel_name = f"チケット{ticket_number} - {user.display_name}"

        category_id = await load_ticket_category(guild.id)
        category = guild.get_channel(category_id) if category_id else None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        }

        for rid in mention_roles:
            role = guild.get_role(rid)
            if role:
                overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        channel = await guild.create_text_channel(channel_name, overwrites=overwrites, category=category)

        now = datetime.datetime.now(JST).strftime("%H:%M:%S")
        ticket_logs[channel.id] = [f"{now} - {user}がチケットを作成しました。"]

        await interaction.response.send_message(f"<:check:1394240622310850580> チケットを作成しました: {channel.mention}", ephemeral=True)

        embed = discord.Embed(
            color=discord.Color.green()
        )
        embed.set_author(name=f"{user}がチケットを作成しました。", icon_url=user.display_avatar.url)

        if mentions_text:
            await channel.send(
                content=mentions_text,
                embed=embed,
                view=TicketCloseView(owner_id=interaction.user.id),
                allowed_mentions=discord.AllowedMentions(roles=True, users=False, everyone=False)
            )
        else:
            await channel.send(
                embed=embed,
                view=TicketCloseView(owner_id=interaction.user.id)
            )

class TicketCloseView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=None)
        self.owner_id = owner_id

    @discord.ui.button(
        label="チケットを閉じる",
        style=discord.ButtonStyle.danger,
        custom_id="tickettool:close"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        guild = interaction.guild
        member = guild.get_member(self.owner_id)

        if member:
            await channel.set_permissions(member, view_channel=False, send_messages=False, read_message_history=False)

        now = datetime.datetime.now(JST).strftime("%H:%M:%S")
        ticket_logs[channel.id].append(f"{now} - {interaction.user}がチケットを閉じました。")

        today = datetime.datetime.now().strftime("%Y-%m-%d")
        filename = f"ticketArchived-{interaction.user}-{today}.txt"

        file_content = "\n".join(ticket_logs[channel.id])
        file = discord.File(io.BytesIO(file_content.encode("utf-8")), filename=filename)

        close_emb = discord.Embed(
            color=discord.Color.red()
        )
        close_emb.set_author(name=f"{interaction.user}がチケットを閉じました。", icon_url=interaction.user.display_avatar.url)

        await channel.send(file=file, embed=close_emb, view=TicketReopenDeleteView(self.owner_id))

        await interaction.followup.send("<:check:1394240622310850580> チケットを閉じました。", ephemeral=True)


class TicketReopenDeleteView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=None)
        self.owner_id = owner_id

    @discord.ui.button(
        label="元に戻す",
        style=discord.ButtonStyle.success,
        custom_id="tickettool:reopen"
    )
    async def reopen_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        guild = interaction.guild
        member = guild.get_member(self.owner_id)
        if not member:
            await interaction.followup.send("<:cross:1394240624202481705> 所有者が見つかりません。", ephemeral=True)
            return

        await channel.set_permissions(member, view_channel=True, send_messages=True, read_message_history=True)

        try:
            await interaction.message.edit(view=None)
        except Exception:
            pass

        now = datetime.datetime.now(JST).strftime("%H:%M:%S")
        ticket_logs[channel.id].append(f"{now} - {interaction.user}がチケットを再開しました。")

        emb = discord.Embed(
            color=discord.Color.green()
        )
        emb.set_author(name=f"{interaction.user}がチケットを再開しました。", icon_url=interaction.user.display_avatar.url)
        await channel.send(embed=emb)

        await interaction.followup.send("<:check:1394240622310850580> チケットを再開しました。", ephemeral=True)


    @discord.ui.button(
        label="削除",
        style=discord.ButtonStyle.danger,
        custom_id="tickettool:delete"
    )
    async def delete_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 削除は即実行（必要なら権限チェックを入れてください）
        await interaction.response.defer(ephemeral=True)
        await interaction.followup.send("チケットを削除しています...", ephemeral=True)
        # 削除する前に必要なログ保存などがあればここで行う
        await interaction.channel.delete()



# ========== 設定パネル（永続ボタン） ==========
class MentionsPanel(discord.ui.View):
    """再起動後も動く永続パネル"""

    def __init__(self):
        super().__init__(timeout=None)  # 永続

    async def _ensure_admin(self, interaction: discord.Interaction) -> bool:
        if not interaction.user.guild_permissions.manage_guild:
            await interaction.response.send_message(
                "この操作には管理者権限が必要です。", ephemeral=True
            )
            return False
        return True

    async def _refresh_panel(self, interaction: discord.Interaction):
        guild = interaction.guild
        role_ids = await load_role_ids(guild.id)
        embed = build_panel_embed(guild, role_ids)
        await interaction.message.edit(embed=embed, view=self)

    # --- ロール追加 ---
    @discord.ui.button(
        label="ロール追加", style=discord.ButtonStyle.success,
    custom_id="tickettool:mentions:add", emoji="<:plus:1394231723390275645>"
    )
    async def add_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ensure_admin(interaction):
            return

        class AddRoleView(discord.ui.View):
            def __init__(self, parent: MentionsPanel):
                super().__init__(timeout=60)
                self.parent = parent

                self.role_select = discord.ui.RoleSelect(
                    placeholder="追加したいロールを選んでください（複数可）",
                    min_values=1,
                    max_values=25
                )
                self.role_select.callback = self.role_picker
                self.add_item(self.role_select)

            async def role_picker(self, itx: discord.Interaction):
                picked: List[discord.Role] = list(self.role_select.values)
                role_ids = await load_role_ids(itx.guild.id)

                for r in picked:
                    if r.id not in role_ids:
                        role_ids.append(r.id)

                await save_role_ids(itx.guild.id, role_ids)

                # ✅ 削除と同じように、ユーザーのephemeralメッセージを編集
                await itx.response.edit_message(content="<:check:1394240622310850580>追加しました。", view=None)

                # ✅ 管理用パネルを更新
                await MentionsPanel()._refresh_panel(interaction)

        v = AddRoleView(self)
        await interaction.response.send_message(
            "追加したいロールを選んでください。", view=v, ephemeral=True
        )

    # --- ロール削除 ---
    @discord.ui.button(
        label="ロール削除", style=discord.ButtonStyle.danger, custom_id="tickettool:mentions:remove", emoji="<:minus:1394231720995197158>"
    )
    async def remove_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ensure_admin(interaction):
            return

        current_ids = await load_role_ids(interaction.guild.id)
        options: List[discord.SelectOption] = []
        for rid in current_ids:
            role = interaction.guild.get_role(rid)
            label = role.name if role else f"不明なロール ({rid})"
            options.append(discord.SelectOption(label=label, value=str(rid)))

        if not options:
            await interaction.response.send_message("<:warn:1394241229176311888>設定されているロールがありません。", ephemeral=True)
            return

        class RemoveRoleView(discord.ui.View):
            def __init__(self, opts: List[discord.SelectOption]):
                super().__init__(timeout=60)
                self.select = discord.ui.Select(
                    placeholder="削除するロールを選んでください",
                    min_values=1,
                    max_values=len(opts),
                    options=opts,
                )
                self.select.callback = self._on_select  # type: ignore
                self.add_item(self.select)

            async def _on_select(self, itx: discord.Interaction):
                chosen = [int(v) for v in self.select.values]
                role_ids = await load_role_ids(itx.guild.id)
                role_ids = [rid for rid in role_ids if rid not in chosen]
                await save_role_ids(itx.guild.id, role_ids)

                await itx.response.edit_message(content="<:check:1394240622310850580>削除しました。", view=None)
                await MentionsPanel()._refresh_panel(interaction)

        v = RemoveRoleView(options)
        await interaction.response.send_message("削除するロールを選択してください。", view=v, ephemeral=True)

    # --- 不明なロール削除 ---
    @discord.ui.button(
        label="不明なロール削除", style=discord.ButtonStyle.secondary, custom_id="tickettool:mentions:prune", emoji="<:cross:1394240624202481705>"
    )
    async def prune_unknown(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._ensure_admin(interaction):
            return

        role_ids = await load_role_ids(interaction.guild.id)
        unknown = [rid for rid in role_ids if interaction.guild.get_role(rid) is None]
        if not unknown:
            await interaction.response.send_message("<:check:1394240622310850580>不明なロールはありません。", ephemeral=True)
            return

        role_ids = [rid for rid in role_ids if rid not in unknown]
        await save_role_ids(interaction.guild.id, role_ids)
        await interaction.response.send_message(
            f"<:check:1394240622310850580>{len(unknown)} 件の不明なロールを削除しました。", ephemeral=True
        )
        await self._refresh_panel(interaction)

# ========== Cog 本体 ==========
class TicketMentions(commands.Cog):
    """tickettool mentions 設定UI（MongoDB永続化）"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.add_view(MentionsPanel())     # メンション設定パネル
        bot.add_view(TicketOpenView())    # チケット作成ボタン



    @commands.hybrid_group(name="tickettool", description="チケットツールの設定をします。")
    async def tickettool(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.reply("使用方法:`z!tickettool create` または `z!tickettool mentions`")

    @tickettool.command(name="mentions", description="チケットツールのメンション設定を変更します。")
    async def tickettool_mentions(self, ctx: commands.Context):
        guild = ctx.guild
        if not guild:
            return
        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("<:cross:1394240624202481705>このコマンドを実行するには管理者権限が必要です。", ephemeral=True)
            return

        role_ids = await load_role_ids(guild.id)
        embed = build_panel_embed(guild, role_ids)
        view = MentionsPanel()
        await ctx.reply(embed=embed, view=view)

    @tickettool.command(
        name="create",
        description="チケット作成パネルを送信します。"
    )
    @app_commands.describe(channel="パネル送信先")
    @app_commands.rename(channel="チャンネル")
    async def tickettool_panel(
        self,
        ctx: commands.Context,
        channel: discord.TextChannel  # 作成先チャンネルを引数に
    ):
        guild = ctx.guild
        if not guild:
            return

        if not ctx.author.guild_permissions.manage_guild:
            await ctx.reply("<:cross:1394240624202481705> このコマンドを実行するには管理者権限が必要です。", ephemeral=True)
            return

        category_id = channel.category_id
        await save_ticket_category(guild.id, category_id)

        embed = discord.Embed(
            title="<:ticket:1414217916206813337>サポートチケット",
            description="下のボタンを押すとサポートチケットが作成されます。",
            color=discord.Color.green()
        )

        # 永続ビューを使用（TicketOpenView）
        view = TicketOpenView()

        # パネルを指定チャンネルに送信
        await channel.send(embed=embed, view=view)
        await ctx.reply(f"<:check:1394240622310850580> チケットパネルを{channel.mention}に送信しました。", ephemeral=True)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return
        if message.channel.id not in ticket_logs:
            return
        now = datetime.datetime.now(JST).strftime("%H:%M:%S")
        log_entry = f"{now} - {message.author} - {message.content}"
        ticket_logs[message.channel.id].append(log_entry)


    def get_current_mention_roles(self, guild: discord.Guild) -> List[discord.Role]:
        return []

async def setup(bot: commands.Bot):
    await bot.add_cog(TicketMentions(bot))
