import discord
from discord.ext import commands
from discord.ui import View, Button

EMOJIS_PER_PAGE = 15

class EmojiPaginator(View):
    def __init__(self, ctx: commands.Context, emojis: list[discord.Emoji]):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.emojis = emojis
        self.page = 0
        self.total_pages = (len(emojis) - 1) // EMOJIS_PER_PAGE + 1
        self.message = None

        self.prev_button = Button(
            emoji="<:leftSort:1401175053973848085>",
            style=discord.ButtonStyle.secondary
        )
        self.prev_button.callback = self.prev_page

        self.next_button = Button(
            emoji="<:rightSort:1401174996574801950>",
            style=discord.ButtonStyle.secondary
        )
        self.next_button.callback = self.next_page

        self.update_buttons()
        self.add_item(self.prev_button)
        self.add_item(self.next_button)

    def update_buttons(self):
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= self.total_pages - 1

    def get_page_embed(self):
        start = self.page * EMOJIS_PER_PAGE
        end = start + EMOJIS_PER_PAGE
        page_emojis = self.emojis[start:end]

        desc = ""
        for emoji in page_emojis:
            desc += f"{emoji} `:{emoji.name}:`（`{emoji.id}`）\n"

        embed = discord.Embed(
            title=f"<:emojis:1401177044519223306>絵文字一覧（{self.page + 1}/{self.total_pages}ページ）",
            description=desc or "<:warn:1394241229176311888>このページには絵文字がありません。",
            color=discord.Color.green()
        )
        embed.set_footer(text=f"{len(self.emojis)}個のカスタム絵文字があります")
        return embed

    async def prev_page(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return

        self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    async def next_page(self, interaction: discord.Interaction):
        if interaction.user != self.ctx.author:
            return

        self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_page_embed(), view=self)

    async def on_timeout(self):
        # ⛔ タイムアウト時に全ボタンを無効化し再描画
        for item in self.children:
            if isinstance(item, Button):
                item.disabled = True
        if self.message:
            await self.message.edit(view=self)


class Emoji(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="emojis", description="このサーバーのカスタム絵文字をページごとに表示します。")
    async def emojis(self, ctx: commands.Context):
        emojis = ctx.guild.emojis
        if not emojis:
            return await ctx.send("<:warn:1394241229176311888>このサーバーにはカスタム絵文字がありません。")

        view = EmojiPaginator(ctx, emojis)
        embed = view.get_page_embed()
        view.message = await ctx.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(Emoji(bot))
