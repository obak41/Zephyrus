import discord
from discord.ext import commands, tasks
import os
import json
import sys
import subprocess
import asyncio
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True
intents.voice_states = True

bot = commands.AutoShardedBot(command_prefix="z!", intents=intents, help_command=None)

# ===botの導入情報送信===
load_dotenv(dotenv_path="cogs/.env")
AUTH_KEY = os.getenv("PHP_AUTH_KEY")
PHP_URL = "PHP_URL_HERE"

# ===== 許可するユーザーID =====
ALLOWED_USER_IDS = [
    1000000000000000001, 1000000000000000002, 1000000000000000003

]

# ===== コマンド制限デコレータ =====
def is_owner_user():
    async def predicate(ctx):
        return ctx.author.id in ALLOWED_USER_IDS
    return commands.check(predicate)

# 表示内容を切り替えるためのインデックス
status_index = 0

@tasks.loop(seconds=20)
async def status_task():
    await bot.wait_until_ready()
    global status_index
    
    total_guilds = len(bot.guilds)
    total_users = sum(g.member_count for g in bot.guilds if g.member_count)
    
    # --- Discord上のステータス更新 ---
    if status_index == 0:
        activity_name = f"{total_guilds}サーバー | {total_users}ユーザー"
        status_index = 1
    else:
        activity_name = f"{bot.command_prefix}help"
        status_index = 0
        
    activity = discord.Game(name=activity_name)
    await bot.change_presence(status=discord.Status.online, activity=activity)

    # --- サーバーへのデータ送信 ---
    try:
        # シャードごとの情報を収集
        shard_info = []
        for shard_id, shard in bot.shards.items():
            shard_info.append({
                "id": shard_id,
                "status": "Online" if not shard.is_closed() else "Offline",
                "latency": round(shard.latency * 1000)
            })

        # Web側に送るデータセット
        jst = timezone(timedelta(hours=+9), 'JST')
        now_jst = datetime.now(jst)

        # Web側に送るデータセット
        status_payload = {
            "overall": "Online",
            "server_count": total_guilds,
            "user_count": total_users,
            "shards": shard_info,
            "last_update": now_jst.strftime("%Y/%m/%d %H:%M:%S") # JSTでフォーマット
        }

        # 送信実行
        requests.post(PHP_URL, data={
            "key": AUTH_KEY,
            "data": json.dumps(status_payload)
        }, timeout=5)

    except Exception as e:
        print(f"Web status update error: {e}")

# ===== 起動時イベント =====
@bot.event
async def on_ready():
    print(f"Bot name:{bot.user}")
    print(f"Bot ID:{bot.user.id}")
    print(f"READY!")
    
    if not status_task.is_running():
        status_task.start()

@bot.event
async def setup_hook():
    print("Loading cog...")
    loaded_cog = 0
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            await bot.load_extension(f'cogs.{filename[:-3]}')
            print(f"Loaded cog: {filename}")
            loaded_cog = loaded_cog + 1
    print(f"Loaded {loaded_cog} cog(s).")
    # スラッシュコマンドを同期
    await bot.tree.sync()
    print("Synced slash commands.")

# ===== Cog管理コマンド群 =====

@bot.command(name="load")
@is_owner_user()
async def load_cog(ctx, cog: str):
    try:
        await bot.load_extension(f"cogs.{cog}")
        await ctx.send(f"Successfully loaded {cog}!")
    except Exception as e:
        await ctx.send(f"Error while loading `{cog}`: `{e}`")

@bot.command(name="reload")
@is_owner_user()
async def reload_cog(ctx, cog: str):
    try:
        await bot.reload_extension(f"cogs.{cog}")
        await ctx.send(f"Successfully reloaded {cog}!")
    except Exception as e:
        await ctx.send(f"Error while reloading `{cog}`: `{e}`")

@bot.command(name="unload")
@is_owner_user()
async def unload_cog(ctx, cog: str):
    try:
        await bot.unload_extension(f"cogs.{cog}")
        await ctx.send(f"Successfully unloaded {cog}!")
    except Exception as e:
        await ctx.send(f"Error while unloading `{cog}`: `{e}`")

@bot.command(name="listcogs")
@is_owner_user()
async def list_cogs(ctx):
    loaded = list(bot.extensions.keys())
    if not loaded:
        await ctx.send("No Cogs are currently loaded.")
    else:
        cog_list = "\n".join(f"- {cog}" for cog in loaded)
        await ctx.send(f"Cogs currently loading:\n```\n{cog_list}\n```")

@bot.command(name="shutdown")
@is_owner_user()
async def shutdown_bot(ctx):
    await ctx.send("Shutting down...")
    await bot.close()

@bot.command(name="restart")
@is_owner_user()
async def restart_bot(ctx):
    await ctx.send("Restarting bot...")
    await bot.close()
    subprocess.Popen([sys.executable] + sys.argv)
    return

@bot.command(name="sync")
@is_owner_user()
async def sync_commands(ctx: commands.Context):
    try:
        synced = await bot.tree.sync()
        await ctx.send(f"Synced {len(synced)} command(s)!")
    except Exception as e:
        await ctx.send(f"Error while syncing command: `{e}`")

# ===== 権限エラー時のメッセージ =====
@load_cog.error
@reload_cog.error
@unload_cog.error
@list_cogs.error
@sync_commands.error
@shutdown_bot.error
@restart_bot.error
async def cog_permission_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("⚠️You don't have permission to execute this command!")
    else:
        raise error

# ===== Bot起動 =====
with open('config.json') as f:
    config = json.load(f)
    TOKEN = config["token"]

bot.run(TOKEN)
