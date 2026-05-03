import discord
from discord.ext import commands, tasks
from discord import app_commands
import yt_dlp
import asyncio
import datetime
import random
import re
import urllib.request
from collections import deque
import ssl
import os
import aiohttp
from dotenv import load_dotenv
import base64
import urllib.parse
import requests
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

load_dotenv()

# --- 設定 ---
COOKIE_PATH = 'PATH_TO_TXT_FILE'

YDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'default_search': 'ytsearch', # 検索をデフォルトにする
    # 'source_address': '0.0.0.0',
    'nocheckcertificate': True,
    'ignoreerrors': True,
    'no_warnings': True,
    'extract_flat': False,
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -rw_timeout 10000000',
    'options': '-vn -loglevel error'
}

class MusicView(discord.ui.View):
    def __init__(self, bot, player, cog):
        super().__init__(timeout=None)
        self.bot = bot
        self.player = player
        self.cog = cog
        self.update_button_style()

    def update_button_style(self):
        # シャッフルボタンの状態
        self.shuffle.emoji = "<:buttonShuffleOn:1467166216350203946>" if self.player._shuffle_backup else "<:buttonShuffleOff:1467166239804887053>"
        
        # 再生・一時停止ボタンの状態
        vc = self.player.ctx.voice_client
        if vc and vc.is_paused():
            self.play_pause.emoji = "<:buttonPlay:1467166233131483290>"
        else:
            self.play_pause.emoji = "<:buttonPause:1467166229923102731>"
            
        # リピートボタンの状態 (OFF -> Queue -> Current)
        if self.player.loop_current:
            self.loop.emoji = "<:buttonRepeatCurrent:1467166236533199044>"
        elif self.player.loop_queue:
            self.loop.emoji = "<:buttonRepeatOn:1467166238504386664>"
        else:
            self.loop.emoji = "<:buttonRepeatOff:1467166234628849779>"

    def create_embed(self):
        import time
        player = self.player
        data = player.current
        
        # 再生時間のフォーマット
        duration_sec = data.get('duration')
        duration = str(datetime.timedelta(seconds=duration_sec))[2:] if duration_sec else "不明"
        
        title = data.get('title', '不明なタイトル')
        artist = data.get('uploader', '不明なアーティスト')
        
        # リンクの取得（title_url が無ければ original_url を使う）
        t_url = data.get('title_url') or data.get('original_url')
        a_url = data.get('artist_url')

        # --- 重複チェック & Markdown作成 ---
        # 1. 曲名部分の作成
        title_display = f"[{title}]({t_url})" if t_url else title

        # 2. アーティスト名部分の作成（タイトルに含まれていない場合のみ）
        if artist.lower() in title.lower():
            # タイトルにアーティスト名が含まれているなら曲名のみ
            description_text = title_display
        else:
            # 含まれていない場合、アーティスト名もリンク化して結合
            artist_display = f"[{artist}]({a_url})" if a_url else artist
            description_text = f"{title_display} - {artist_display}"
        
        # 3. Embed作成
        embed = discord.Embed(
            title="<:buttonPlay:1467166233131483290> **再生中**",
            description=f"{description_text} `[{duration}]`"
        )

        # 音量表示
        embed.add_field(name="", value=f"音量: **{int(self.player.volume * 100)}%**", inline=False)
        
        # サムネイル（キャッシュ対策付き）
        if data.get('thumbnail'):
            clean_thumb = data['thumbnail'].split('?')[0]
            refreshed_thumb = f"{clean_thumb}?v={int(time.time())}"
            embed.set_thumbnail(url=refreshed_thumb)
        
        return embed

    @discord.ui.button(custom_id="shuffle", row=0)
    async def shuffle(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 1. キューの確認
        if not self.player.queue and self.player._shuffle_backup is None:
            return await interaction.response.send_message("<:warn:1394241229176311888> キューが空です。", ephemeral=True)

        # 2. シャッフル / 復元ロジック
        if self.player._shuffle_backup is not None:
            # 復元ロジック：履歴(URL)にある曲を除外
            played_urls = {h['url'] for h in self.player.history}
            restored = [s for s in self.player._shuffle_backup if s['url'] not in played_urls]
            self.player.queue = deque(restored)
            self.player._shuffle_backup = None
        else:
            # シャッフル実行
            self.player._shuffle_backup = list(self.player.queue)
            temp = list(self.player.queue)
            random.shuffle(temp)
            self.player.queue = deque(temp)

        # 3. ボタンの見た目を更新（self.update_button_styleがある前提）
        self.update_button_style()

        # 4. メッセージを更新 (edit_original_response から変更)
        # これにより Interaction 404 エラーを回避します
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(emoji="<:prev:1401175547719192628>", row=0)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.player.history:
            return await interaction.response.send_message("履歴がありません。", ephemeral=True)
        
        await interaction.response.defer()

        # 1. 本当に1つ前の曲を取り出す
        prev_track = self.player.history.pop()

        # 2. キューの先頭に [前の曲, 今の曲] の順で戻す
        # これにより IRIS -> KICK -> JANE の時に戻すと KICK が再生され、
        # その次（キューの2番目）に JANE が待機する形になります
        self.player.queue.appendleft(self.player.current)
        self.player.queue.appendleft(prev_track)

        # 3. 戻るボタン専用フラグを立てる (after_playing で履歴追加をスキップさせる)
        self.player.is_prev = True

        if interaction.guild.voice_client:
            interaction.guild.voice_client.stop()

    @discord.ui.button(custom_id="play_pause", row=0)
    async def play_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        vc = interaction.guild.voice_client
        if vc.is_playing():
            vc.pause()
        else:
            vc.resume()
        self.update_button_style()
        await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(emoji="<:skip:1401175525069946920>", row=0)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        interaction.guild.voice_client.stop()

    @discord.ui.button(custom_id="loop", row=0)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        # OFF -> Queue -> Current -> OFF の順で切り替え
        if not self.player.loop_queue and not self.player.loop_current:
            self.player.loop_queue = True
        elif self.player.loop_queue:
            self.player.loop_queue = False
            self.player.loop_current = True
        else:
            self.player.loop_current = False
            
        self.update_button_style()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(emoji="<:buttonList:1467170042993971301>", row=1)
    async def queue_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.player.queue:
            return await interaction.response.send_message("キューは空です。", ephemeral=True)
        msg = "\n".join([f"{i+1}. {s['title']}" for i, s in enumerate(list(self.player.queue)[:10])])
        await interaction.response.send_message(f"**キュー一覧 (先頭10曲):**\n{msg}", ephemeral=True)

    @discord.ui.button(emoji="<:buttonVolDown:1467171222956544112>", row=1)
    async def vol_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.volume = max(0.0, self.player.volume - 0.1)
        if interaction.guild.voice_client.source:
            interaction.guild.voice_client.source.volume = self.player.volume
        await interaction.response.edit_message(embed=self.create_embed())

    @discord.ui.button(emoji="<:buttonStop:1467166219659513856>", row=1)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.queue.clear()
        self.player.current = None
        
        if interaction.guild.voice_client:
            await interaction.guild.voice_client.channel.edit(status=None)
            await interaction.guild.voice_client.disconnect()
        await interaction.response.send_message("<:buttonStop:1467166219659513856> 停止しました。", ephemeral=True)

    @discord.ui.button(emoji="<:buttonVolUp:1467171224579997913>", row=1)
    async def vol_up(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.player.volume = min(1.0, self.player.volume + 0.1)
        if interaction.guild.voice_client.source:
            interaction.guild.voice_client.source.volume = self.player.volume
        await interaction.response.edit_message(embed=self.create_embed())

    @discord.ui.button(emoji="<:buttonInfo:1467171796603109396>", row=1)
    async def info(self, interaction: discord.Interaction, button: discord.ui.Button):
        d = self.player.current
        if not d:
            return await interaction.response.send_message("現在再生中の曲はありません。", ephemeral=True)

        embed = self.cog.create_embed(interaction, d, "曲の情報")
    
        try:
            embed.clear_fields()
        
            # タイトル
            title_display = f"[{d['title']}]({d.get('title_url')})" if d.get('title_url') else d['title']
            embed.add_field(name="タイトル", value=title_display, inline=False)
        
            # アーティスト
            artist_display = f"[{d['uploader']}]({d.get('artist_url')})" if d.get('artist_url') else d['uploader']
            embed.add_field(name="アーティスト", value=artist_display, inline=True)
        
            # アルバム
            album_val = d.get('album', '不明')
            album_display = f"[{album_val}]({d.get('album_url')})" if d.get('album_url') and album_val != '不明' else album_val
            embed.add_field(name="アルバム", value=album_display, inline=True)
        
            # 曲の長さ（秒を変換）
            duration_sec = d.get('duration')
            if duration_sec:
                duration = str(datetime.timedelta(seconds=duration_sec))
                if duration.startswith("0:"): duration = duration[2:]
            else:
                duration = "不明"
        
            embed.add_field(name="曲の長さ", value=duration, inline=False)
        
        except Exception as e:
            # エラーが起きた場合は安全のために既存のフィールドを一部上書きするのみに留める
            print(f"Embed adjustment error: {e}")
            embed.set_field_at(3, name="状態", value="再生中", inline=True)

        await interaction.response.send_message(embed=embed, ephemeral=True)

class MusicPlayer:
    def __init__(self, ctx):
        self.ctx = ctx
        self.queue = deque()
        self.history = deque()
        self.current = None
        self.volume = 0.5
        self.loop_queue = False
        self.loop_current = False
        self.last_active = datetime.datetime.now()
        self.play_and_leave = False
        self._shuffle_backup = None
        self.np_message = None
        self.text_channel = ctx.channel
        self.is_loading = False

class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players = {}
        self.check_vc_status.start()
        auth_manager = SpotifyClientCredentials(
            client_id=os.getenv("SPOTIFY_CLIENT_ID"),
            client_secret=os.getenv("SPOTIFY_CLIENT_SECRET")
        )
        self.sp = spotipy.Spotify(auth_manager=auth_manager)

    def get_player(self, ctx):
        if ctx.guild.id not in self.players:
            player = MusicPlayer(ctx)
            player.last_active = datetime.datetime.now()
            self.players[ctx.guild.id] = player
        return self.players[ctx.guild.id]

    async def get_spotify_metadata(self, target):
        try:
            # 1. 単体トラックの処理
            if 'track' in target:
                t = self.sp.track(target)
                return {
                    "type": "track",
                    "title": t['name'],
                    "artist": t['artists'][0]['name'],
                    "artist_url": t['artists'][0]['external_urls']['spotify'],
                    "album": t['album']['name'],
                    "album_url": t['album']['external_urls']['spotify'],
                    "thumbnail": t['album']['images'][0]['url'],
                    "title_url": t['external_urls']['spotify'],
                    "original_url": target,
                    "duration": t['duration_ms'] // 1000
                }

            # 2. アルバムの処理
            elif 'album' in target:
                try:
                    content_id = target.split('album/')[1].split('?')[0]
                except IndexError:
                    return None

                data = self.sp.album(content_id)
                tracks_obj = data.get('tracks', data)
                raw_items = tracks_obj.get('items', [])
                parsed_tracks = []

                for item in raw_items:
                    if not item: continue
                    # アルバム内楽曲の画像は、アルバム自体のアートワークを使用
                    track_thumbnail = data['images'][0]['url'] if data.get('images') else None

                    parsed_tracks.append({
                        'title': item['name'],
                        'duration': item.get('duration_ms', 0) // 1000,
                        'link': item.get('external_urls', {}).get('spotify'),
                        'artist': {
                            'name': item['artists'][0]['name'] if item.get('artists') else "不明",
                            'id': item['artists'][0]['id'] if item.get('artists') else None
                        },
                        'album': data.get('name'),
                        'thumbnail': track_thumbnail 
                    })

                return {
                    "type": "album",
                    "title": data.get('name', '不明なアルバム'),
                    "artist": data['artists'][0]['name'] if data.get('artists') else '不明',
                    "album": data.get('name'),
                    "thumbnail": data['images'][0]['url'] if data.get('images') else None,
                    "title_url": data.get('external_urls', {}).get('spotify'),
                    "tracks": parsed_tracks
                }

            # 3. プレイリストは拒否
            else:
                if 'artist' in target:
                    return "ARTIST_REJECTED"
                else:
                    return "PLAYLIST_REJECTED"

        except Exception as e:
            print(f"Spotify API Error: {e}")
            return None

        # --- トラック情報のパース ---
        raw_items = tracks_obj.get('items', [])
        parsed_tracks = []

        for item in raw_items:
            if not item: continue

            # プレイリストは item['track']、アルバムは item 直下
            track = item.get('track') if not is_album else item

            if not track or not track.get('name'):
                continue

            # 各曲のアルバム画像を取得するように変更
            track_images = track.get('album', {}).get('images', [])
            # 曲固有の画像があればそれを使い、なければプレイリストの画像で補完
            track_thumbnail = track_images[0]['url'] if track_images else (data['images'][0]['url'] if data.get('images') else None)

            parsed_tracks.append({
                'title': track['name'],
                'duration': track.get('duration_ms', 0) // 1000,
                'link': track.get('external_urls', {}).get('spotify'),
                'artist': {
                    'name': track['artists'][0]['name'] if track.get('artists') else "不明",
                    'id': track['artists'][0]['id'] if track.get('artists') else None
                },
                'thumbnail': track_thumbnail # ここを修正した変数に差し替え
            })

        return {
            "type": "album" if is_album else "playlist",
            "title": data.get('name', '不明なタイトル'),
            "artist": data['artists'][0]['name'] if is_album else data.get('owner', {}).get('display_name', '不明'),
            "thumbnail": data['images'][0]['url'] if data.get('images') else None,
            "title_url": data.get('external_urls', {}).get('spotify'),
            "tracks": parsed_tracks
        }

    async def get_deezer_metadata(self, url):
        def fetch_deezer_location(target_url):
            cookies = {}
            try:
                with open('assets/deezer_cookie.txt', 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('#') or not line.strip(): continue
                        parts = line.split('\t')
                        if len(parts) >= 7:
                            cookies[parts[5]] = parts[6].strip()
            except: pass

            headers = {
                'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
            }

            try:
                # allow_redirects=False で Location ヘッダーだけを引っこ抜く
                resp = requests.get(target_url, headers=headers, cookies=cookies, allow_redirects=False, timeout=5)
                return resp.headers.get('Location')
            except Exception as e:
                print(f"DEBUG: Requests Error: {e}")
                return None

        # 非同期実行で URL を展開
        real_url = await self.bot.loop.run_in_executor(None, fetch_deezer_location, url)
        if not real_url:
            return None

        resource_type = None
        resource_id = None

        decoded_url = urllib.parse.unquote(real_url)
        # 正規表現に artist を追加
        match = re.search(r'(track|album|playlist|artist)/(\d+)', decoded_url)

        if match:
            resource_type = match.group(1)
            resource_id = match.group(2)
        else:
            parts = decoded_url.split('/')
            for i, part in enumerate(parts):
                if part in ['track', 'album', 'playlist', 'artist']:
                    resource_type = part
                    if i + 1 < len(parts):
                        next_part = parts[i+1].split('?')[0]
                        if next_part.isdigit():
                            resource_id = next_part
                    break

        if not resource_id:
            return None

        # --- API URLの決定 ---
        # アーティストの場合はトップトラックを取得するためのエンドポイントへ
        if resource_type == 'artist':
            api_url = f"https://api.deezer.com/artist/{resource_id}/top?limit=10"
        else:
            api_url = f"https://api.deezer.com/{resource_type}/{resource_id}"

        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    # アーティストかつデータが空の場合
                    if resource_type == 'artist' and not data.get('data'):
                        return "ARTIST_TOP_NOT_FOUND" # 固有の識別子を返す

                    if 'error' in data: return None

                    # --- アーティスト特有の処理 ---
                    if resource_type == 'artist':
                        tracks_data = data.get('data', [])
                        if not tracks_data:
                            return "ARTIST_TOP_NOT_FOUND"

                        # 1曲目のデータからアーティスト情報を取得
                        first_track = tracks_data[0]
                        artist_info = first_track.get('artist', {})
                        artist_name = artist_info.get('name', '不明')
                        contributors = first_track.get('contributors', [])
        
                        # ご提示の "picture" フィールドを優先的に参照し、なければサイズ指定版を探す
                        print(contributors)
                        raw_artist_img = contributors[0].get('picture_xl')
                        
                        if raw_artist_img:
                            artist_img = raw_artist_img.replace('\\/', '/')
                        else:
                            artist_img = None
                        
                        print(raw_artist_img)
                        print(artist_img)

                        res = {
                            "type": "artist_top",
                            "title": f"{artist_name} - 人気曲",
                            "title_url": f"https://www.deezer.com/artist/{resource_id}",
                            "thumbnail": artist_img, # ここに https://api.deezer.com/artist/ID/image が入る
                            "artist": artist_name,
                            "artist_url": f"https://www.deezer.com/artist/{resource_id}",
                            "track_count": len(tracks_data),
                            "duration": sum(t.get('duration', 0) for t in tracks_data),
                            "tracks": []
                        }

                        for t in tracks_data:
                            t_album = t.get('album', {})
                            res["tracks"].append({
                                "title": t.get('title'),
                                "duration": t.get('duration'),
                                "link": t.get('link'),
                                "artist": t.get('artist', {}),
                                "album": t_album.get('title', '不明'),
                                "thumbnail": t_album.get('cover_xl') or t_album.get('cover_big')
                            })
                        return res

                    # --- 既存の track/album/playlist 処理 ---
                    raw_thumbnail = (
                        data.get('cover_xl') or 
                        data.get('album', {}).get('cover_xl') or
                        data.get('cover_big') or 
                        data.get('album', {}).get('cover_big') or 
                        data.get('picture_xl') or
                        data.get('artist', {}).get('picture_xl')
                    )
                    clean_thumbnail = raw_thumbnail.replace('//', '/').replace('https:/', 'https://') if raw_thumbnail else None

                    res = {
                        "type": resource_type,
                        "title": data.get('title') or data.get('name'),
                        "title_url": data.get('link'),
                        "thumbnail": clean_thumbnail,
                        "track_count": data.get('nb_tracks', 1),
                        "duration": data.get('duration', 0),
                        "tracks": []
                    }

                    if resource_type == 'playlist':
                        res["artist"] = data.get('creator', {}).get('name', '不明')
                        res["artist_url"] = f"https://www.deezer.com/profile/{data.get('creator', {}).get('id')}"
                    else:
                        res["artist"] = data.get('artist', {}).get('name', '不明')
                        res["artist_url"] = data.get('artist', {}).get('link')

                    if resource_type == 'track':
                        album_data = data.get('album', {})
                        album_name = album_data.get('title', '不明')
                        album_url = f"https://www.deezer.com/album/{album_data.get('id')}" if album_data.get('id') else None
                        
                        # process_music_input の B（単体曲）が参照するトップレベルにデータを追加
                        res["album"] = album_name
                        res["album_url"] = album_url
                        
                        # 既存の tracks リストへの追加（ここも整合性を合わせる）
                        res["tracks"].append({
                            "title": data.get('title'),
                            "duration": data.get('duration'),
                            "link": data.get('link'),
                            "artist": data.get('artist', {}),
                            "album": album_name
                        })
                    else:
                        track_data = data.get('tracks', {}).get('data', [])
                        for t in track_data:
                            t_album = t.get('album', {})
                            res["tracks"].append({
                                "title": t.get('title'),
                                "duration": t.get('duration'),
                                "link": t.get('link'),
                                "artist": t.get('artist', {}),
                                "album": t_album.get('title') or data.get('title') or '不明',
                                "thumbnail": t_album.get('cover_xl') or t_album.get('cover_big')
                            })
                    return res
        return None
    
    async def fetch_info(self, target):
        rich_meta = None
        
        # サービスの判定（URL文字列を正しく判定）
        is_deezer = "deezer.com" in target
        is_spotify = "open.spotify.com" in target
        
        if not (is_deezer or is_spotify):
            return None, "forbidden_service"

        if is_deezer:
            rich_meta = await self.get_deezer_metadata(target)
        elif is_spotify:
            rich_meta = await self.get_spotify_metadata(target)

        # プレイリスト拒否の戻り値をそのまま上に流す
        if rich_meta == "PLAYLIST_REJECTED":
            return None, "PLAYLIST_REJECTED"
        
        if rich_meta == "ARTIST_REJECTED":
            return None, "ARTIST_REJECTED"

        if not rich_meta:
            return None, "meta_fetch_error"

        query = f"ytsearch:{rich_meta['title']} {rich_meta['artist']} topic"
        info = await self._get_info(query)
        
        return info, rich_meta

    async def _get_info(self, query):
        opts = YDL_OPTIONS.copy()
        opts.update({
            'extract_flat': False,
            'process_true': True,
            'format': 'bestaudio/best',
        })
        
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                # 実行スレッドを分ける
                info = await self.bot.loop.run_in_executor(
                    None, lambda: ydl.extract_info(query, download=False)
                )
                
                if not info:
                    return None
                    
                # 検索結果（entries）がある場合
                if 'entries' in info:
                    if not info['entries']:
                        return None
                    return info['entries'][0]
                
                return info
            except Exception as e:
                print(f"yt-dlp fetch error: {e}")
                return None

    async def cog_before_invoke(self, ctx):
        if ctx.command.name in ["join"]: return
        if not ctx.author.voice:
            await ctx.reply("<:warn:1394241229176311888> 先にボイスチャンネルに接続してください。", ephemeral=True)

    async def process_music_input(self, ctx, target, is_insert=False):
        player = self.get_player(ctx)
        player.text_channel = ctx.channel
        player.is_loading = True

        # --- 古いゾンビセッションの強制排除 ---
        vc = ctx.guild.voice_client
        
        # 1. vcが存在するが、接続状態が不安定（is_connectedがFalse）な場合は強制切断
        if vc and not vc.is_connected():
            try:
                await vc.disconnect(force=True)
                await asyncio.sleep(1.5) # Discord側が切断を認識するまで待機
                vc = None
            except:
                pass

        # 2. まったく別のチャンネルに一人で残っている場合なども考慮し、一端リセットを試みる
        # (すでに再生中の場合はスルー、止まっている場合のみ実行)
        if vc and not vc.is_playing() and not vc.is_paused():
            if vc.channel.id != ctx.author.voice.channel.id:
                 await vc.disconnect(force=True)
                 await asyncio.sleep(1.0)
                 vc = None

        # --- 新規接続処理 ---
        if not vc:
            if not ctx.author.voice:
                return await ctx.send("<:cross:1394240624202481705> ボイスチャンネルに参加してからコマンドを使用してください。")
            
            try:
                # タイムアウトを長めに設定し、reconnect=Trueでライブラリ側の再試行を有効化
                vc = await ctx.author.voice.channel.connect(self_deaf=True, timeout=60.0, reconnect=True)
            except asyncio.TimeoutError:
                return await ctx.send("<:cross:1394240624202481705> 接続がタイムアウトしました。リージョンを変更して試してください。")
            except Exception as e:
                return await ctx.send(f"<:cross:1394240624202481705> 接続失敗: {e}")
        elif vc.channel.id != ctx.author.voice.channel.id:
            await vc.move_to(ctx.author.voice.channel)
        
        # 接続直後の安定時間を確保
        await asyncio.sleep(2)
        
        # 1. メタデータ取得
        info, rich_meta = await self.fetch_info(target)
    
        if rich_meta == "PLAYLIST_REJECTED":
            return await ctx.send("<:warn:1394241229176311888> 現在、Spotifyのプレイリストには対応していません。")

        if rich_meta == "ARTIST_REJECTED":
            return await ctx.send("<:warn:1394241229176311888> 現在、SpotifyのアーティストURLには対応していません。")

        if rich_meta == "ARTIST_TOP_NOT_FOUND":
            return await ctx.send("<:warn:1394241229176311888> 指定されたアーティストの人気曲が見つかりませんでした。")
            
        if info is None and (not rich_meta or "tracks" not in rich_meta):
            if rich_meta == "forbidden_service":
                # Tidalを消したので文言を修正
                return await ctx.send("<:warn:1394241229176311888> 現在対応しているサービスは Spotify、Deezer のみです。")
            return await ctx.send("<:cross:1394240624202481705> 曲の情報が取得できませんでした。")

        # --- A. 複数曲（Spotify / Deezer 共通） ---
        if rich_meta and rich_meta.get('type') in ['album', 'playlist', 'artist_top']:
            player.last_active = datetime.datetime.now() # 即切断防止
            await ctx.send(embed=self.create_collection_embed(ctx, rich_meta))

            for track_info in rich_meta['tracks']:
                # SpotifyかDeezerかでリンクのキーが違う可能性を考慮
                track_link = track_info.get('link') or track_info.get('url')
                
                artist_obj = track_info.get('artist', {})
                artist_name = artist_obj.get('name') or rich_meta.get('artist')
                
                # アーティストURLの生成
                if track_link and "spotify" in track_link:
                    a_id = artist_obj.get('id')
                    artist_url = f"https://open.spotify.com/artist/{a_id}" if a_id else None
                else:
                    a_id = artist_obj.get('id')
                    artist_url = f"https://www.deezer.com/artist/{a_id}" if a_id else None

                t_data = {
                    'url': None, # YouTube検索前なのでNone
                    'title': track_info.get('title'),
                    'duration': track_info.get('duration'),
                    'uploader': artist_name,
                    'album': track_info.get('album', '不明'),
                    'thumbnail': track_info.get('thumbnail') or rich_meta.get('thumbnail'),
                    'original_url': track_link, # これが start_playing での検索に使われる
                    'title_url': track_link,    # これが Embed でのクリック用リンクになる
                    'artist_url': artist_url,
                }
                
                # アーティストの人気曲の場合は順次後ろに追加
                player.queue.append(t_data)

            # 再生開始
            if not vc.is_playing() and not vc.is_paused():
                await self.start_playing(ctx)
            return

        # --- B. 単体曲の場合（YouTube または Deezerの1曲URLなど） ---
        # ここで rich_meta がある場合と info しかない場合を統合して data を作る
        data = {
            'url': info.get('url') if info else None,
            'title': rich_meta['title'] if (rich_meta and 'title' in rich_meta) else info.get('title'),
            'title_url': rich_meta.get('title_url') if rich_meta else None,
            'duration': info.get('duration') if info else rich_meta.get('duration'),
            'uploader': rich_meta['artist'] if (rich_meta and 'artist' in rich_meta) else info.get('uploader'),
            'artist_url': rich_meta.get('artist_url') if rich_meta else None,
            'album': rich_meta.get('album') or '不明', 
            'album_url': rich_meta.get('album_url') if rich_meta else None,
            'thumbnail': rich_meta.get('thumbnail') if rich_meta else info.get('thumbnail'),
            'original_url': target,
        }

        # 再生中かどうかにかかわらず、まずはキューに追加
        if is_insert: 
            player.queue.appendleft(data)
        else: 
            player.queue.append(data)

        if not vc.is_playing() and not vc.is_paused():
            # 即再生
            await self.start_playing(ctx)
        else:
            # 「キューに追加」メッセージ（下のほうを使いたいという部分）を表示
            title_text = "次に再生" if is_insert else "キューに追加"
            await ctx.send(embed=self.create_embed(ctx, data, title_text))

    def create_embed(self, ctx_or_interaction, data, title_text):
        if isinstance(ctx_or_interaction, discord.Interaction):
            user = ctx_or_interaction.user
            guild_id = ctx_or_interaction.guild_id
        else:
            user = ctx_or_interaction.author
            guild_id = ctx_or_interaction.guild.id
            
        player = self.players.get(guild_id)
        duration_sec = data.get('duration')
        
        # 秒を MM:SS 形式に変換
        if duration_sec:
            duration = str(datetime.timedelta(seconds=duration_sec))
            if duration.startswith("0:"): duration = duration[2:]
        else:
            duration = "不明"
        
        embed = discord.Embed(title=title_text, color=0x2f3136)
        
        # タイトル (Deezerリンク)
        title_display = f"[{data['title']}]({data.get('title_url')})" if data.get('title_url') else data['title']
        embed.add_field(name="タイトル", value=title_display, inline=False)
        
        # アーティスト
        artist_display = f"[{data['uploader']}]({data.get('artist_url')})" if data.get('artist_url') else data['uploader']
        embed.add_field(name="アーティスト", value=artist_display, inline=True)
        
        # アルバム
        album_val = data.get('album', '不明')
        album_display = f"[{album_val}]({data.get('album_url')})" if data.get('album_url') and album_val != '不明' else album_val
        embed.add_field(name="アルバム", value=album_display, inline=True)
        
        # その他
        pos = f"{len(player.queue)}番目" if title_text == "キューに追加" else "次"
        embed.add_field(name="キューの位置", value=pos, inline=True)
        embed.add_field(name="曲の長さ", value=duration, inline=True)
        
        if data.get('thumbnail'):
            embed.set_thumbnail(url=data['thumbnail'])
        
        embed.set_footer(text=f"Requested by {user.display_name}", icon_url=user.display_avatar.url)
        return embed
        
    # --- 追加: アルバム/プレイリスト専用Embed作成関数 ---
    def create_collection_embed(self, ctx, meta):
        # 1. 曲数と合計時間の計算 (KeyError対策)
        tracks = meta.get('tracks', [])
        track_count = meta.get('track_count') or len(tracks)
        
        # durationが無い場合は全トラックの合計を計算
        duration_sec = meta.get('duration')
        if duration_sec is None:
            duration_sec = sum(t.get('duration', 0) for t in tracks)

        # 秒を HH:MM:SS または MM:SS に変換
        duration_str = str(datetime.timedelta(seconds=duration_sec))
        if duration_str.startswith("0:"): 
            duration_str = duration_str[2:]

        # 各サービスのブランドカラー設定
        service_colors = {
            "spotify": 0x1DB954,  # Spotifyグリーン
            "deezer": 0x00C7FF    # Deezerライトブルー
        }

        # URLからサービスを判定して色を決定
        title_url = meta.get('title_url', '').lower()
        embed_color = 0x2f3136  # デフォルト色
        
        for service, color in service_colors.items():
            if service in title_url:
                embed_color = color
                break

        # --- 2. Embedのタイプ判定とラベルの決定 ---
        m_type = meta.get('type')
        if m_type == 'artist_top':
            col_type_label = f"アーティストの人気曲({track_count}曲)"
            artist_label = "アーティスト"
        elif m_type == 'playlist':
            col_type_label = "プレイリスト"
            artist_label = "作成者"
        else:
            col_type_label = "アルバム"
            artist_label = "アーティスト"

        embed = discord.Embed(title=f"{col_type_label}をキューに追加", color=embed_color)

        # アーティスト/作成者 (リンク付き)
        a_url = meta.get('artist_url')
        artist_display = f"[{meta.get('artist', '不明')}]({a_url})" if a_url else meta.get('artist', '不明')
        
        # フィールドの追加 (提供されたレイアウトを維持)
        embed.add_field(name=artist_label, value=artist_display, inline=True)
        
        # 「合計の長さ」または「曲の長さ」として表示
        len_label = "曲の長さ" if m_type == 'artist_top' else "合計の長さ"
        embed.add_field(name=len_label, value=duration_str, inline=True)

        # アルバム/プレイリスト名がある場合は追加 (artist_top 以外の場合に表示)
        if m_type != 'artist_top':
            t_url = meta.get('title_url')
            title_value = f"[{meta.get('title', '不明')}]({t_url})" if t_url else meta.get('title', '不明')
            embed.add_field(name="タイトル", value=title_value, inline=False)
            
            # 曲数 (アルバム・プレイリスト時のみ追加)
            embed.add_field(name="曲数", value=f"{track_count}曲", inline=True)

        # --- サムネイルの設定 ---
        # ここで meta['thumbnail'] をセットすることで右側に画像が出ます
        if meta.get('thumbnail'):
            embed.set_thumbnail(url=meta['thumbnail'])

        # フッター
        embed.set_footer(
            text=f"Requested by {ctx.author.display_name}", 
            icon_url=ctx.author.display_avatar.url
        )
        
        return embed

    @tasks.loop(seconds=30)
    async def check_vc_status(self):
        now = datetime.datetime.now()
        for guild_id, player in list(self.players.items()):
            vc = player.ctx.voice_client 
            if not vc: continue

            # --- 最優先判定：人がいるかどうか ---
            # 自分(bot)以外の人間を探す
            members = [m for m in vc.channel.members if not m.bot]

            if not members:
                # 人がいなければ、再生中であっても即切断
                try:
                    await vc.channel.edit(status=None)
                except:
                    pass
                await vc.disconnect()

                if player.text_channel:
                    await player.text_channel.send("<:warn:1394241229176311888> ボイスチャンネルに人がいないため、切断しました。")

                if guild_id in self.players:
                    del self.players[guild_id]
                continue # 次のギルドの処理へ

            # --- 次の判定：再生中かどうかの放置チェック ---
            # 準備中(is_loading) または 再生中 または キューがある なら放置時間をリセット
            is_active = (
                vc.is_playing() or 
                vc.is_paused() or 
                player.current is not None or 
                player.is_loading or
                len(player.queue) > 0
            )

            if is_active:
                player.last_active = now
                continue # アクティブならここで終了して次のループへ

            # --- 最後の判定：何もせず放置されている時間の計算 ---
            idle_time = (now - player.last_active).total_seconds()

            # 曲が止まってから300秒（5分）経過したら切断
            if idle_time > 300:
                print(f"DEBUG: Disconnecting {guild_id}. Idle Time: {idle_time}s")
                try:
                    await vc.channel.edit(status=None)
                except:
                    pass
                await vc.disconnect()

                if player.text_channel:
                    await player.text_channel.send(f"<:warn:1394241229176311888> 5分間曲を再生していないため、切断しました。")

                if guild_id in self.players:
                    del self.players[guild_id]

    @commands.hybrid_group(name="music", description="音楽機能のメインコマンド", aliases=["m"])
    async def music(self, ctx):
        await ctx.send("使用方法:`zd!music clear`, `zd!music insert [URLまたは曲名]`, `zd!music join`, `zd!music leave`, `zd!music play [URLまたは曲名]`, `zd!music previous`, `zd!music queue`, `zd!music repeat-current`, `zd!music repeat-queue`, `zd!music resume`, `zd!music seek [秒数]`, `zd!music skip`, `zd!music songinfo`, `zd1music stop`, `zd!music volume [音量]`", ephemeral=True)

    @music.command(name="play", description="音楽を再生します", aliases=["p"])
    @commands.guild_only()
    @app_commands.rename(input="urlまたは曲名")
    async def play(self, ctx, *, input: str = None):
        await ctx.defer()
        target = ctx.message.attachments[0].url if ctx.message.attachments else input
        await self.process_music_input(ctx, target, is_insert=False)
        

    @music.command(name="insert", description="曲を次に再生に追加します。", aliases=["ins"])
    @commands.guild_only()
    @app_commands.rename(input="urlまたは曲名")
    async def insert(self, ctx, *, input: str = None):
        await ctx.defer()
        target = ctx.message.attachments[0].url if ctx.message.attachments else input
        await self.process_music_input(ctx, target, is_insert=True)

    async def start_playing(self, ctx, seek_time=None):
        player = self.get_player(ctx)
        player.last_active = datetime.datetime.now()

        if not player.queue:
            player.is_loading = False
            return

        player.is_loading = True 
        data = player.queue.popleft()

        # --- ここで変数を初期化しておく (スコープエラー対策) ---
        search_query = None 

        try:
            # URLのリフレッシュ処理
            orig = data.get('original_url', '')
            if any(s in (orig or "") for s in ["deezer", "spotify"]):
                title = data['title']
                artist = data['uploader']
                if artist != '不明なアーティスト' and artist not in title:
                    search_query = f"ytsearch:{title} {artist} topic"
                else:
                    search_query = f"ytsearch:{title} topic"
            else:
                search_query = orig or data['title']

            print(f"DEBUG: Refreshing URL for query: {search_query}")
            fresh_info = await self._get_info(search_query)
        
            # (中略: fresh_info のチェック)
            if fresh_info and isinstance(fresh_info, dict) and 'url' in fresh_info:
                data['url'] = fresh_info['url']
            else:
                # 見つからなかった場合、次の曲を探しに行く前に一瞬 loading を True に保つ
                print(f"DEBUG: Track not found, skipping to next.")
                player.is_loading = True 
                return self.bot.loop.create_task(self.start_playing(ctx))

            player.current = data
            opts = FFMPEG_OPTIONS.copy()
            if seek_time: opts['before_options'] += f" -ss {seek_time}"

            if not ctx.voice_client:
                player.is_loading = False
                return

            # --- after_playing の定義 ---
            def after_playing(error):
                if error: print(f"Player error: {error}")

                if player.np_message:
                    self.bot.loop.create_task(self.delete_message_safe(player.np_message))

                if player.loop_current: 
                    player.queue.appendleft(data)
                elif player.loop_queue: 
                    player.queue.append(data)

                # --- 履歴への追加判定 (is_prevを使用) ---
                if getattr(player, 'is_prev', False):
                    player.is_prev = False  # フラグをリセット
                    print("DEBUG: Prev button pressed, skipping history append.")
                else:
                    # 履歴に追加するのは search_query ではなく data
                    player.history.append(data)

                self.bot.loop.create_task(ctx.author.voice.channel.edit(status=None))
                player.last_active = datetime.datetime.now()
                self.bot.loop.create_task(self.start_playing(ctx))

            ffmpeg_audio = discord.FFmpegPCMAudio(
                data['url'], 
                executable='ffmpeg', 
                **opts
            )

            source = discord.PCMVolumeTransformer(
                ffmpeg_audio, 
                volume=player.volume
            )

            # --- ボイスチャンネルのステータスを更新 ---
            try:
                # 再生する曲の情報をステータス文字にする
                # 例: "再生中: 曲名 - アーティスト"
                new_status = f"再生中: {data['title']} - {data['uploader']}"
                
                # 50文字制限があるため、超える場合はカット
                if len(new_status) > 50:
                    new_status = new_status[:47] + "..."
                
                # ボイスチャンネルのステータスを書き換え
                await ctx.author.voice.channel.edit(status=new_status)
            except Exception as e:
                print(f"DEBUG: Failed to update VC status: {e}")
    
            ctx.voice_client.play(source, after=after_playing)
            player.is_loading = False

            if player.np_message:
                self.bot.loop.create_task(self.delete_message_safe(player.np_message))

            view = MusicView(self.bot, player, self)
            player.np_message = await ctx.channel.send(embed=view.create_embed(), view=view)

        except Exception as e:
            print(f"Playback error in start_playing: {e}") # どこでエラーが出たか分かりやすく
            player.is_loading = False
            self.bot.loop.create_task(self.start_playing(ctx))

    # 安全にメッセージを消すための補助関数
    async def delete_message_safe(self, message):
        try:
            await message.delete()
        except Exception:
            # 既に消されている場合や権限がない場合のエラーを無視
            pass

    @music.command(name="pause", description="音楽を一時停止します。")
    @commands.guild_only()
    async def pause(self, ctx):
        if ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            self.get_player(ctx).last_active = datetime.datetime.now()
            await ctx.send(f"<:buttonPause:1467166229923102731> 一時停止しました。")

    @music.command(name="resume", description="音楽の再生を再開します。")
    @commands.guild_only()
    async def resume(self, ctx):
        if ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send(f"<:buttonPlay:1467166233131483290> 再開しました。")

    @music.command(name="join", description="ボイスチャンネルに参加します。")
    @commands.guild_only()
    async def join(self, ctx):
        await ctx.author.voice.channel.connect()
        await ctx.send(f"<:check:1394240622310850580> ボイスチャンネルに参加しました。")

    @music.command(name="leave", description="ボイスチャンネルから退出します。")
    @commands.guild_only()
    async def leave(self, ctx):
        await self.stop(ctx)
        await ctx.send(f"<:check:1394240622310850580> ボイスチャンネルから退出しました。")

    @music.command(name="seek", description="指定した時間に移動します")
    @app_commands.rename(seconds="秒数")
    @commands.guild_only()
    async def seek(self, ctx, seconds: int):
        if ctx.interaction:
            await ctx.defer()
        player = self.get_player(ctx)
        if not player.current: 
            return await ctx.send(f"<:warn:1394241229176311888> 現在再生中の曲がありません。")
        
        current_data = player.current.copy()
        player.queue.appendleft(current_data)
        
        player.is_seeking = True 
        
        if ctx.voice_client:
            ctx.voice_client.stop()
            
        seek_timestamp = str(datetime.timedelta(seconds=seconds))
        
        await self.start_playing(ctx, seek_time=seek_timestamp)
        await ctx.send(f"<:check:1394240622310850580> {seconds}秒地点に移動しました。")

    @music.command(name="skip", description="現在の曲をスキップします。")
    @commands.guild_only()
    async def skip(self, ctx):
        if ctx.voice_client:
            ctx.voice_client.stop()
            await ctx.send(f"<:check:1394240622310850580> スキップしました。")

    @music.command(name="previous", description="前の曲に戻ります。", aliases=["prev"])
    @commands.guild_only()
    async def previous(self, ctx):
        player = self.get_player(ctx)
        if not player.history: 
            return await ctx.send(f"<:warn:1394241229176311888> 履歴がありません。")
        
        prev_song = player.history.pop()
        
        if player.current:
            player.queue.appendleft(player.current.copy())
            
        player.queue.appendleft(prev_song)
        
        if ctx.voice_client:
            player.is_backtracking = True 
            ctx.voice_client.stop()
            
        await ctx.send(f"<:check:1394240622310850580> 前の曲に戻ります。")

    @music.command(name="stop", description="再生を完全に停止し、VCから退出します。", aliases=["dc"])
    @commands.guild_only()
    async def stop(self, ctx):
        player = self.get_player(ctx)
        player.queue.clear()
        if ctx.voice_client:
            if ctx.author.voice:
                await ctx.author.voice.channel.edit(status=None)
            await ctx.voice_client.disconnect()
            if ctx.guild.id in self.players: del self.players[ctx.guild.id]
        await ctx.send(f"<:buttonStop:1467166219659513856> 停止しました。")

    @music.command(name="volume", description="音量を設定します (0-100)。", aliases=["vol"])
    @app_commands.rename(vol="音量")
    @commands.guild_only()
    async def volume(self, ctx, vol: int):
        if 0 <= vol <= 100:
            player = self.get_player(ctx)
            player.volume = vol / 100
            if ctx.voice_client.source: ctx.voice_client.source.volume = player.volume
            await ctx.send(f"音量: {vol}%")

    @music.command(name="shuffle", description="キューをシャッフルします。")
    @commands.guild_only()
    async def shuffle(self, ctx):
        player = self.get_player(ctx)
        random.shuffle(player.queue)
        await ctx.send("シャッフルしました。")

    @music.command(name="repeat-queue", description="キューループを切り替えます。", aliases=["rq"])
    @commands.guild_only()
    async def repeat_queue(self, ctx):
        player = self.get_player(ctx)
        player.loop_queue = not player.loop_queue
        await ctx.send(f"キューループ: {'ON' if player.loop_queue else 'OFF'}")

    @music.command(name="repeat-current", description="1曲ループを切り替えます。", aliases=["rc"])
    @commands.guild_only()
    async def repeat_current(self, ctx):
        player = self.get_player(ctx)
        player.loop_current = not player.loop_current
        await ctx.send(f"1曲ループ: {'ON' if player.loop_current else 'OFF'}")

    @music.command(name="clear", description="キューを全削除します。")
    @commands.guild_only()
    async def clear(self, ctx):
        self.get_player(ctx).queue.clear()
        await ctx.send("キューをクリアしました。")

    @music.command(name="queue", description="現在のキューを表示します。")
    @commands.guild_only()
    async def queue(self, ctx):
        player = self.get_player(ctx)
        if not player.queue: return await ctx.send("キューは空です。")
        msg = "\n".join([f"{i+1}. {s['title']}" for i, s in enumerate(list(player.queue)[:10])])
        await ctx.send(f"**キュー一覧:**\n{msg}")

    @music.command(name="songinfo", description="再生中の曲の詳細を表示します。", aliases=["si"])
    @commands.guild_only()
    async def songinfo(self, ctx):
        # ハイブリッドコマンドのタイムアウト対策
        if ctx.interaction:
            await ctx.interaction.response.defer()

        player = self.get_player(ctx)
        d = player.current
        
        if not d:
            return await ctx.send("<:warn:1394241229176311888> 現在再生中の曲はありません。")

        # create_embed を利用。ctx を渡す。
        embed = self.create_embed(ctx, d, "曲の情報")
        
        try:
            embed.clear_fields()
            
            # 1. タイトル
            # ボタン側のロジックと同様に title_url を優先。なければ webpage_url を予備にするのもアリ
            title_url = d.get('title_url') or d.get('webpage_url')
            title_display = f"[{d['title']}]({title_url})" if title_url else d['title']
            embed.add_field(name="タイトル", value=title_display, inline=False)
            
            # 2. アーティスト
            artist_display = f"[{d['uploader']}]({d.get('artist_url')})" if d.get('artist_url') else d['uploader']
            embed.add_field(name="アーティスト", value=artist_display, inline=True)
            
            # 3. アルバム
            album_val = d.get('album', '不明')
            album_display = f"[{album_val}]({d.get('album_url')})" if d.get('album_url') and album_val != '不明' else album_val
            embed.add_field(name="アルバム", value=album_display, inline=True)
            
            # 4. 曲の長さ
            duration_sec = d.get('duration')
            if duration_sec:
                duration = str(datetime.timedelta(seconds=duration_sec))
                if duration.startswith("0:"): duration = duration[2:]
            else:
                duration = "不明"
            
            embed.add_field(name="曲の長さ", value=duration, inline=True)
            
            # コマンド版なので「状態」も追加しておくと親切
            embed.add_field(name="状態", value="再生中", inline=True)
            
        except Exception as e:
            print(f"Embed adjustment error: {e}")

        await ctx.send(embed=embed)

async def setup(bot):
    await bot.add_cog(Music(bot))
