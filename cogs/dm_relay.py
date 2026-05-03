import discord
from discord.ext import commands
import re

class DMRelay(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log_channel_id = 1433816223426150531
        self.webhooks = {}
        self.thread_user_map = {}
        self.message_link_map = {}

    async def get_or_create_webhook(self, channel: discord.TextChannel):
        if channel.id in self.webhooks:
            return self.webhooks[channel.id]

        webhooks = await channel.webhooks()
        webhook = discord.utils.get(webhooks, name="Zephyrus DM Notification")
        if not webhook:
            webhook = await channel.create_webhook(name="Zephyrus DM Notification")

        self.webhooks[channel.id] = webhook
        return webhook

    # ============================================================
    # メッセージ送信イベント (DM→スレッド, スレッド→DM)
    # ============================================================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # ------------------ DMからのメッセージ ------------------
        if isinstance(message.channel, discord.DMChannel):
            log_channel = self.bot.get_channel(self.log_channel_id)
            if not log_channel:
                return

            display_name = message.author.display_name
            thread_name = f"DM-{display_name}-{message.author.id}"

            # スレッドを検索または作成
            thread = discord.utils.get(log_channel.threads, name=thread_name)
            if not thread:
                thread = await log_channel.create_thread(
                    name=thread_name,
                    type=discord.ChannelType.public_thread
                )

            self.thread_user_map[thread.id] = message.author.id
            webhook = await self.get_or_create_webhook(log_channel)
            files = [await a.to_file() for a in message.attachments]

            webhook_msg = await webhook.send(
                content=message.content or "",
                username=f"{message.author.display_name}",
                avatar_url=message.author.display_avatar.url,
                files=files,
                thread=thread,
                wait=True
            )

            # --- 双方向リンク保存 ---
            self.message_link_map[message.id] = webhook_msg.id
            self.message_link_map[webhook_msg.id] = message.id
            return

        # ------------------ スレッドでのメッセージ ------------------
        if isinstance(message.channel, discord.Thread) and message.channel.parent_id == self.log_channel_id:
            thread = message.channel
            log_channel = thread.parent
            webhook = await self.get_or_create_webhook(log_channel)

            user_id = self.thread_user_map.get(thread.id)
            if not user_id:
                match = re.match(r"DM-(.+)-(\d+)", thread.name)
                if match:
                    user_id = int(match.group(2))
                    self.thread_user_map[thread.id] = user_id
            if not user_id:
                return

            user = self.bot.get_user(user_id)
            if not user:
                return

            files = [await a.to_file() for a in message.attachments]

            try:
                sent_msg = await user.send(content=message.content or "", files=files)

                # --- 双方向リンク保存 ---
                self.message_link_map[message.id] = sent_msg.id
                self.message_link_map[sent_msg.id] = message.id

            except discord.Forbidden:
                await thread.send("<:warn:1394241229176311888> DMを送信できませんでした。", delete_after=5)

    # ============================================================
    # メッセージ編集イベント (双方向同期)
    # ============================================================
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if after.author.bot or before.content == after.content:
            return

        # --- 編集元がDMの場合 ---
        if isinstance(after.channel, discord.DMChannel):
            linked_id = self.message_link_map.get(after.id)
            if not linked_id:
                return

            log_channel = self.bot.get_channel(self.log_channel_id)
            webhook = await self.get_or_create_webhook(log_channel)

            for thread in log_channel.threads:
                try:
                    # Webhook経由のメッセージを編集する
                    await webhook.edit_message(linked_id, content=after.content, thread=thread)
                    break
                except discord.NotFound:
                    continue
                except discord.Forbidden:
                    continue


        # --- 編集元がスレッド(Webhook経由)の場合 ---
        elif isinstance(after.channel, discord.Thread) and after.channel.parent_id == self.log_channel_id:
            linked_id = self.message_link_map.get(after.id)
            if not linked_id:
                return
            try:
                # 対応するDMメッセージを取得して編集
                user_id = self.thread_user_map.get(after.channel.id)
                if not user_id:
                    match = re.match(r"DM-(.+)-(\d+)", after.channel.name)
                    if match:
                        user_id = int(match.group(2))
                        self.thread_user_map[after.channel.id] = user_id
                if not user_id:
                    return

                user = self.bot.get_user(user_id)
                if not user:
                    return

                dm = await user.create_dm()
                msg = await dm.fetch_message(linked_id)
                await msg.edit(content=after.content)
            except discord.NotFound:
                pass

async def setup(bot):
    await bot.add_cog(DMRelay(bot))
