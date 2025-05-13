import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import yt_dlp
from collections import deque
import asyncio
import random
import time
import json
import re
from typing import Optional, List, Dict, Any

# Create bot instance
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

node_ffmpeg = os.path.join(os.getcwd(), 'node_modules', 'ffmpeg-static', 'ffmpeg')

os.environ["FFMPEG_BINARY"] = node_ffmpeg

print(f"Using ffmpeg at: {node_ffmpeg}")
print(f"File exists: {os.path.exists(node_ffmpeg)}")

load_dotenv()
TOKEN = os.getenv("TOKEN")

# Global variables with optimized initialization
SONG_QUEUES = {}
VOLUME_LEVELS = {}
SONG_HISTORY = {}
SONG_RATINGS = {}
CUSTOM_PLAYLISTS = {}
CURRENT_TRACKS = {}
VOICE_CHANNEL_LOCKS = {}
AUTO_JOIN_CHANNELS = {}
FILTERS = {}
SONG_TIMESTAMPS = {}
NIGHTCORE_ENABLED = {}
EQUALIZER_SETTINGS = {}
AUDIO_BALANCE = {}
LANGUAGE_PREFERENCES = {}
ACTIVE_GAME_SESSIONS = {}
SONG_CACHE = {}
VISUALIZER_ACTIVE = {}

SUPPORTED_LANGUAGES = {
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
    "nl": "Dutch"
}

AVAILABLE_FILTERS = {
    "bassboost":
    "aresample=48000,aformat=sample_fmts=s16:channel_layouts=stereo,bass=g=10",
    "nightcore":
    "aresample=48000,asetrate=48000*1.25,aformat=sample_fmts=s16:channel_layouts=stereo",
    "8d": "apulsator=hz=0.09",
    "vaporwave":
    "aresample=48000,asetrate=48000*0.8,aformat=sample_fmts=s16:channel_layouts=stereo",
    "tremolo": "tremolo=f=6.0:d=0.8",
    "vibrato": "vibrato=f=6.5:d=0.5",
    "reverse": "areverse",
    "normalizer": "dynaudnorm=f=200",
    "echo": "aecho=0.8:0.88:60:0.4"
}

# Optimized yt-dlp configuration
# Optimized and fixed yt-dlp configuration
ydl_opts_base = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,  # Changed to extract complete info
    "socket_timeout": 10,  # Increased timeout
    "source_address": "0.0.0.0",
    "force-ipv4": True,
    "youtube_skip_dash_manifest": True,
    "nocheckcertificate": True,  # Added for SSL certificate issues
    "ignoreerrors": True,  # Added to ignore some errors
    "extractor_args": {
        "youtube": {
            "skip": ["translated_subs"]
        }
    }
}

async def search_ytdlp_async(query, ydl_opts):
    if query in SONG_CACHE:
        return SONG_CACHE[query]
        
    loop = asyncio.get_running_loop()
    try:
        result = await loop.run_in_executor(None, lambda: _extract(query, ydl_opts))
        SONG_CACHE[query] = result
        return result
    except Exception as e:
        print(f"YT-DLP error: {str(e)}")
        raise

def _extract(query, ydl_opts):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(query, download=False)
            return info
        except Exception as e:
            print(f"Extraction error: {str(e)}")
            raise


async def prefetch_next_track(guild_id, voice_client):
    guild_id_str = str(guild_id)
    if guild_id_str in SONG_QUEUES and len(SONG_QUEUES[guild_id_str]) > 0:
        next_track = SONG_QUEUES[guild_id_str][0]
        try:
            if not hasattr(next_track, 'url'):
                results = await search_ytdlp_async(next_track[1],
                                                   ydl_opts_base)
                if "entries" in results:
                    next_track_info = results["entries"][0]
                else:
                    next_track_info = results
                SONG_QUEUES[guild_id_str][0] = (next_track_info["url"],
                                                next_track_info["title"],
                                                next_track_info["duration"])
        except Exception as e:
            print(f"Prefetch error: {e}")


def get_ffmpeg_options(guild_id):
    filters = FILTERS.get(str(guild_id), [])

    if NIGHTCORE_ENABLED.get(str(guild_id),
                             False) and "nightcore" not in filters:
        filters.append("nightcore")

    ffmpeg_options = {
        "before_options":
        "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin",
        "options": "-vn -threads 2",
    }

    if filters:
        filter_string = ",".join(
            [AVAILABLE_FILTERS[f] for f in filters if f in AVAILABLE_FILTERS])
        if filter_string:
            ffmpeg_options["options"] += f" -af \"{filter_string}\""

    return ffmpeg_options


def get_track_info(track):
    """Extract and validate track information from yt-dlp results"""
    # Handle common format issues
    if not track:
        return {
            "title": "Unknown",
            "url": "",
            "webpage_url": "",
            "thumbnail": "",
            "duration": 0,
            "uploader": "Unknown",
            "view_count": 0,
            "id": ""
        }
    
    # Check for direct URL in formats
    direct_url = None
    if "formats" in track and track["formats"]:
        for fmt in track["formats"]:
            if fmt.get("url") and fmt.get("acodec") != "none":
                direct_url = fmt.get("url")
                break
    
    # Fall back to the main URL if no format URLs found
    final_url = direct_url or track.get("url", "")
    
    # Debugging
    if not final_url:
        print(f"Warning: No playable URL found for track {track.get('title', 'Unknown')}")
        print(f"Available keys: {list(track.keys())}")
    
    return {
        "title": track.get("title", "Unknown"),
        "url": final_url,
        "webpage_url": track.get("webpage_url", track.get("original_url", "")),
        "thumbnail": track.get("thumbnail", ""),
        "duration": track.get("duration", 0),
        "uploader": track.get("uploader", "Unknown"),
        "view_count": track.get("view_count", 0),
        "id": track.get("id", "")
    }


def format_duration(seconds):
    if not seconds:
        return "Unknown"

    minutes, seconds = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"


def calculate_queue_time(guild_id):
    queue = SONG_QUEUES.get(str(guild_id), deque())
    total_time = 0
    for _, _, duration in queue:
        total_time += duration or 0
    return total_time


def save_data():
    data = {
        "song_ratings": SONG_RATINGS,
        "custom_playlists": CUSTOM_PLAYLISTS,
        "voice_channel_locks": VOICE_CHANNEL_LOCKS,
        "auto_join_channels": AUTO_JOIN_CHANNELS,
        "equalizer_settings": EQUALIZER_SETTINGS,
        "language_preferences": LANGUAGE_PREFERENCES,
    }

    with open("music_bot_data.json", "w") as f:
        json.dump(data, f)


def load_data():
    global SONG_RATINGS, CUSTOM_PLAYLISTS, VOICE_CHANNEL_LOCKS, AUTO_JOIN_CHANNELS, EQUALIZER_SETTINGS, LANGUAGE_PREFERENCES

    try:
        with open("music_bot_data.json", "r") as f:
            data = json.load(f)

        SONG_RATINGS = data.get("song_ratings", {})
        CUSTOM_PLAYLISTS = data.get("custom_playlists", {})
        VOICE_CHANNEL_LOCKS = data.get("voice_channel_locks", {})
        AUTO_JOIN_CHANNELS = data.get("auto_join_channels", {})
        EQUALIZER_SETTINGS = data.get("equalizer_settings", {})
        LANGUAGE_PREFERENCES = data.get("language_preferences", {})
    except (FileNotFoundError, json.JSONDecodeError):
        pass


async def play_next_song(voice_client, guild_id, channel):
    guild_id_str = str(guild_id)
    
    if not voice_client or not voice_client.is_connected():
        SONG_QUEUES[guild_id_str] = deque()
        return
    
    if SONG_QUEUES[guild_id_str]:
        audio_url, title, duration = SONG_QUEUES[guild_id_str].popleft()
        
        CURRENT_TRACKS[guild_id_str] = {
            "title": title,
            "url": audio_url,
            "started_at": time.time(),
            "duration": duration
        }
        
        SONG_TIMESTAMPS[guild_id_str] = 0
        ffmpeg_options = get_ffmpeg_options(guild_id)
        
        try:
            # Verify audio URL is valid and accessible
            if not audio_url or not isinstance(audio_url, str):
                raise ValueError(f"Invalid audio URL: {audio_url}")
            
            # Check if ffmpeg is installed and accessible
            import subprocess
            try:
                subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
            except (FileNotFoundError, subprocess.SubprocessError):
                raise RuntimeError("FFmpeg is not installed or not found in PATH. Please install FFmpeg.")
            
            source = discord.FFmpegPCMAudio(audio_url, **ffmpeg_options, executable="ffmpeg")
            volume = VOLUME_LEVELS.get(guild_id_str, 0.5)
            source = discord.PCMVolumeTransformer(source, volume=volume)
            
            def after_play(error):
                if error:
                    asyncio.run_coroutine_threadsafe(
                        channel.send(f"⚠️ Error during playback: {error}"), bot.loop)
                    print(f"Playback error for {title}: {error}")
                
                if guild_id_str not in SONG_HISTORY:
                    SONG_HISTORY[guild_id_str] = []
                if len(SONG_HISTORY[guild_id_str]) >= 50:
                    SONG_HISTORY[guild_id_str].pop(0)
                SONG_HISTORY[guild_id_str].append((audio_url, title, duration))
                
                # Prefetch next track while current one is ending
                asyncio.create_task(prefetch_next_track(guild_id, voice_client))
                
                asyncio.run_coroutine_threadsafe(play_next_song(voice_client, guild_id, channel), bot.loop)
            
            voice_client.play(source, after=after_play)
            
            embed = discord.Embed(
                title="🎵 Now Playing",
                description=f"**{title}**",
                color=discord.Color.green()
            )
            if duration:
                embed.add_field(name="Duration", value=format_duration(duration))
            
            await channel.send(embed=embed)
            
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"Play next song error:\n{error_trace}")
            await channel.send(f"⚠️ Error playing track: {str(e)}")
            # Try to play the next song after a short delay
            await asyncio.sleep(1)
            asyncio.create_task(play_next_song(voice_client, guild_id, channel))
    else:
        if guild_id_str in CURRENT_TRACKS:
            del CURRENT_TRACKS[guild_id_str]


@bot.event
async def on_ready():
    print(f"{bot.user} is online!")
    load_data()

    async def sync_commands():
        retries = 3
        for attempt in range(retries):
            try:
                synced_commands = await bot.tree.sync()
                print(f"Synced {len(synced_commands)} global commands")

                commands = bot.tree.get_commands()
                print(f"Registered {len(commands)} commands:")
                for cmd in commands:
                    print(f"- /{cmd.name}")
                return True
            except Exception as e:
                wait_time = (attempt + 1) * 5
                print(
                    f"Sync attempt {attempt + 1} failed (retry in {wait_time}s): {e}"
                )
                await asyncio.sleep(wait_time)
        return False

    if not await sync_commands():
        print("Failed to sync commands after retries")

    async def auto_save_data():
        while True:
            await asyncio.sleep(300)
            save_data()
            print("Data auto-saved")

    bot.loop.create_task(auto_save_data())


@bot.event
async def on_voice_state_update(member, before, after):
    if member.id == bot.user.id and after.channel is None:
        # Bot was disconnected from voice
        guild_id_str = str(before.channel.guild.id)
        if guild_id_str in SONG_QUEUES:
            SONG_QUEUES[guild_id_str].clear()
        if guild_id_str in CURRENT_TRACKS:
            del CURRENT_TRACKS[guild_id_str]
        print(f"Bot was disconnected from voice in {before.channel.guild.name}")
        return
        
    if member.bot:
        return
    
    if before.channel is None and after.channel is not None:
        user_id_str = str(member.id)
        guild_id_str = str(member.guild.id)
        
        if user_id_str in AUTO_JOIN_CHANNELS and guild_id_str in AUTO_JOIN_CHANNELS[user_id_str]:
            if str(after.channel.id) == AUTO_JOIN_CHANNELS[user_id_str][guild_id_str]:
                if not member.guild.voice_client or not member.guild.voice_client.is_connected():
                    try:
                        await after.channel.connect()
                    except Exception as e:
                        print(f"Auto-join error: {e}")
    
    if before.channel is not None and len(before.channel.members) == 1:
        if before.channel.members[0].id == bot.user.id:
            voice_client = before.channel.guild.voice_client
            if voice_client and voice_client.is_connected():
                await voice_client.disconnect()
                guild_id_str = str(before.channel.guild.id)
                if guild_id_str in SONG_QUEUES:
                    SONG_QUEUES[guild_id_str].clear()
                if guild_id_str in CURRENT_TRACKS:
                    del CURRENT_TRACKS[guild_id_str]


@bot.tree.command(name="play", description="Play a song or add it to the queue.")
@app_commands.describe(song_query="Search query or YouTube URL")
async def play(interaction: discord.Interaction, song_query: str):
    # Respond immediately with a "processing" message
    await interaction.response.send_message("🔍 Searching for your song...")
    
    if not interaction.user.voice:
        return await interaction.edit_original_response(content="❌ You must be in a voice channel to use this command.")
        
    voice_channel = interaction.user.voice.channel
    guild_id_str = str(interaction.guild_id)
    
    if guild_id_str in VOICE_CHANNEL_LOCKS and VOICE_CHANNEL_LOCKS[guild_id_str]:
        if interaction.guild.voice_client and interaction.guild.voice_client.channel != voice_channel:
            return await interaction.edit_original_response(content="❌ Voice channel is locked. The bot can only play in its current channel.")
    
    voice_client = interaction.guild.voice_client
    if voice_client is None:
        try:
            voice_client = await voice_channel.connect(timeout=10.0, reconnect=True, self_deaf=True)
        except Exception as e:
            return await interaction.edit_original_response(content=f"❌ Failed to connect to voice channel: {str(e)}")
    elif voice_channel != voice_client.channel:
        try:
            await voice_client.move_to(voice_channel)
        except Exception as e:
            return await interaction.edit_original_response(content=f"❌ Failed to move to your voice channel: {str(e)}")
    
    if guild_id_str not in SONG_QUEUES:
        SONG_QUEUES[guild_id_str] = deque()
    
    if guild_id_str not in VOLUME_LEVELS:
        VOLUME_LEVELS[guild_id_str] = 0.5
    
    query = song_query
    if not query.startswith("http"):
        query = "ytsearch1:" + song_query
    
    try:
        results = await search_ytdlp_async(query, ydl_opts_base)
        
        if "entries" in results:
            tracks = results["entries"]
            if not tracks:
                return await interaction.edit_original_response(content="❌ No results found.")
            first_track = tracks[0]
        else:
            first_track = results
        
        info = get_track_info(first_track)
        SONG_QUEUES[guild_id_str].append((info["url"], info["title"], info["duration"]))
        
        embed = discord.Embed(
            title="🎵 Track Added",
            color=discord.Color.blue()
        )
        embed.add_field(name="Title", value=info["title"], inline=False)
        
        if info["duration"]:
            embed.add_field(name="Duration", value=format_duration(info["duration"]), inline=True)
            
        if info["uploader"]:
            embed.add_field(name="Uploader", value=info["uploader"], inline=True)
            
        if info["thumbnail"]:
            embed.set_thumbnail(url=info["thumbnail"])
        
        if voice_client.is_playing() or voice_client.is_paused():
            queue_position = len(SONG_QUEUES[guild_id_str])
            embed.description = f"Added to queue at position {queue_position}"
            await interaction.edit_original_response(embed=embed)
        else:
            embed.description = "Starting playback"
            await interaction.edit_original_response(embed=embed)
            await play_next_song(voice_client, interaction.guild_id, interaction.channel)
    
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Play command error:\n{error_trace}")
        await interaction.edit_original_response(content=f"❌ Error: {str(e)}\nCheck console for details.")


@bot.tree.command(name="skipto",
                  description="Skip to a specific song in the queue")
@app_commands.describe(position="Position in the queue (1-based)")
async def skip_to(interaction: discord.Interaction, position: int):
    guild_id_str = str(interaction.guild_id)

    if guild_id_str not in SONG_QUEUES or not SONG_QUEUES[guild_id_str]:
        return await interaction.response.send_message("❌ Queue is empty.")

    if position < 1 or position > len(SONG_QUEUES[guild_id_str]):
        return await interaction.response.send_message(
            f"❌ Invalid position. Queue has {len(SONG_QUEUES[guild_id_str])} songs."
        )

    queue_list = list(SONG_QUEUES[guild_id_str])
    requested_song = queue_list[position - 1]
    SONG_QUEUES[guild_id_str] = deque(queue_list[position - 1:])

    voice_client = interaction.guild.voice_client
    if voice_client and (voice_client.is_playing()
                         or voice_client.is_paused()):
        voice_client.stop()

    await interaction.response.send_message(
        f"⏭️ Skipping to **{requested_song[1]}**")


@bot.tree.command(
    name="nowplaying",
    description="Show information about the currently playing song")
async def now_playing(interaction: discord.Interaction):
    guild_id_str = str(interaction.guild_id)

    if guild_id_str not in CURRENT_TRACKS:
        return await interaction.response.send_message(
            "❌ Nothing is currently playing.")

    current = CURRENT_TRACKS[guild_id_str]
    elapsed = time.time() - current["started_at"]
    elapsed_str = format_duration(elapsed)
    duration_str = format_duration(
        current["duration"]) if current["duration"] else "Unknown"

    embed = discord.Embed(title="🎵 Now Playing",
                          description=f"**{current['title']}**",
                          color=discord.Color.green())

    if current["duration"]:
        progress_percent = min(100, int((elapsed / current["duration"]) * 100))
        bar_length = 20
        filled_length = int(bar_length * progress_percent / 100)
        progress_bar = "▓" * filled_length + "░" * (bar_length - filled_length)
        embed.add_field(name=f"Progress: {progress_percent}%",
                        value=f"`{elapsed_str} {progress_bar} {duration_str}`",
                        inline=False)
    else:
        embed.add_field(name="Time",
                        value=f"Elapsed: {elapsed_str}",
                        inline=True)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="queue", description="Show the current queue")
async def queue(interaction: discord.Interaction):
    guild_id_str = str(interaction.guild_id)

    if guild_id_str not in SONG_QUEUES or not SONG_QUEUES[guild_id_str]:
        return await interaction.response.send_message("❌ Queue is empty.")

    embed = discord.Embed(title="🎵 Current Queue", color=discord.Color.blue())

    if guild_id_str in CURRENT_TRACKS:
        current = CURRENT_TRACKS[guild_id_str]
        embed.add_field(
            name="▶️ Now Playing",
            value=
            f"**{current['title']}** ({format_duration(current['duration'])})",
            inline=False)

    queue_list = list(SONG_QUEUES[guild_id_str])
    queue_text = ""

    for i, (_, title, duration) in enumerate(queue_list[:10]):
        duration_str = format_duration(duration) if duration else "Unknown"
        queue_text += f"{i+1}. **{title}** ({duration_str})\n"

    if queue_list:
        if len(queue_list) > 10:
            queue_text += f"... and {len(queue_list) - 10} more songs"

        embed.add_field(name="📋 Queue", value=queue_text, inline=False)
        total_duration = calculate_queue_time(interaction.guild_id)
        embed.add_field(name="⏱️ Total Queue Duration",
                        value=format_duration(total_duration),
                        inline=True)
        embed.add_field(name="🔢 Total Songs",
                        value=str(len(queue_list)),
                        inline=True)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="clearqueue", description="Clear the current queue")
async def clear_queue(interaction: discord.Interaction):
    guild_id_str = str(interaction.guild_id)

    if guild_id_str not in SONG_QUEUES or not SONG_QUEUES[guild_id_str]:
        return await interaction.response.send_message(
            "❌ Queue is already empty.")

    SONG_QUEUES[guild_id_str].clear()
    await interaction.response.send_message("🧹 Queue has been cleared.")


@bot.tree.command(name="queuetime",
                  description="Estimate total time for the current queue")
async def queue_time_estimator(interaction: discord.Interaction):
    guild_id_str = str(interaction.guild_id)

    if guild_id_str not in SONG_QUEUES or not SONG_QUEUES[guild_id_str]:
        return await interaction.response.send_message("❌ Queue is empty.")

    total_duration = calculate_queue_time(interaction.guild_id)
    completion_time = time.time() + total_duration
    completion_str = time.strftime("%H:%M:%S", time.localtime(completion_time))

    embed = discord.Embed(title="⏱️ Queue Time Estimator",
                          color=discord.Color.blue())

    embed.add_field(name="Total Queue Duration",
                    value=format_duration(total_duration),
                    inline=True)
    embed.add_field(name="Estimated Completion",
                    value=f"~{completion_str}",
                    inline=True)
    embed.add_field(name="Queue Size",
                    value=f"{len(SONG_QUEUES[guild_id_str])} songs",
                    inline=True)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="songrequest",
                  description="Request a song to be added to the queue")
@app_commands.describe(song_query="Song to request")
async def song_request(interaction: discord.Interaction, song_query: str):
    await interaction.response.defer()

    if not interaction.user.voice:
        return await interaction.followup.send(
            "❌ You must be in a voice channel to request songs.")

    voice_channel = interaction.user.voice.channel
    guild_id_str = str(interaction.guild_id)

    voice_client = interaction.guild.voice_client
    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        if guild_id_str in VOICE_CHANNEL_LOCKS and VOICE_CHANNEL_LOCKS[
                guild_id_str]:
            if voice_client.channel != voice_channel:
                return await interaction.followup.send(
                    "❌ Voice channel is locked. Cannot join your channel.")
        await voice_client.move_to(voice_channel)

    if guild_id_str not in SONG_QUEUES:
        SONG_QUEUES[guild_id_str] = deque()

    query = "ytsearch1:" + song_query

    try:
        results = await search_ytdlp_async(query, ydl_opts_base)

        if "entries" in results:
            tracks = results["entries"]
            if not tracks:
                return await interaction.followup.send(
                    "❌ No results found for your request.")
            first_track = tracks[0]
        else:
            first_track = results

        info = get_track_info(first_track)
        SONG_QUEUES[guild_id_str].append(
            (info["url"], info["title"], info["duration"]))

        embed = discord.Embed(
            title="🎵 Song Request Added",
            description=
            f"**{info['title']}** has been added to the queue by {interaction.user.mention}",
            color=discord.Color.green())

        if info["duration"]:
            embed.add_field(name="Duration",
                            value=format_duration(info["duration"]),
                            inline=True)

        queue_position = len(SONG_QUEUES[guild_id_str])
        if voice_client.is_playing() or voice_client.is_paused():
            embed.add_field(name="Queue Position",
                            value=str(queue_position),
                            inline=True)
            estimated_time = calculate_queue_time(
                interaction.guild_id) - info["duration"]
            embed.add_field(name="Estimated Wait",
                            value=format_duration(estimated_time),
                            inline=True)
        else:
            embed.add_field(name="Status", value="Playing next", inline=True)

        await interaction.followup.send(embed=embed)

        if not voice_client.is_playing() and not voice_client.is_paused():
            await play_next_song(voice_client, interaction.guild_id,
                                 interaction.channel)

    except Exception as e:
        await interaction.followup.send(
            f"❌ Error processing song request: {str(e)}")


@bot.tree.command(name="vote",
                  description="Vote for the next song (placeholder)")
@app_commands.describe(option="Option number to vote for")
async def live_song_voting(interaction: discord.Interaction,
                           option: int = None):
    await interaction.response.send_message(
        "🗳️ Live song voting feature is a placeholder in this version. " +
        "In a full implementation, this would allow users to vote on the next song to play."
    )


@bot.tree.command(name="volume", description="Set volume between 1 and 100")
@app_commands.describe(level="Volume level (1 to 100)")
async def volume(interaction: discord.Interaction, level: int):
    if not 1 <= level <= 100:
        return await interaction.response.send_message(
            "❌ Volume must be between 1 and 100.")

    guild_id_str = str(interaction.guild_id)
    VOLUME_LEVELS[guild_id_str] = level / 100.0

    voice_client = interaction.guild.voice_client
    if voice_client and voice_client.source and isinstance(
            voice_client.source, discord.PCMVolumeTransformer):
        voice_client.source.volume = VOLUME_LEVELS[guild_id_str]

    volume_bars = "▓" * (level // 5) + "░" * ((100 - level) // 5)
    await interaction.response.send_message(
        f"🎚️ Volume set to {level}%\n`{volume_bars}`")


@bot.tree.command(
    name="volumelimiter",
    description="Enable volume limiting to prevent audio clipping")
@app_commands.describe(enabled="Enable or disable the volume limiter")
async def volume_limiter(interaction: discord.Interaction, enabled: bool):
    await interaction.response.send_message(
        f"🎚️ Volume limiter {'enabled' if enabled else 'disabled'}. " +
        "This would prevent audio clipping and normalize volume in a full implementation."
    )


@bot.tree.command(name="balance", description="Set left/right channel balance")
@app_commands.describe(left="Left channel volume (0-100)",
                       right="Right channel volume (0-100)")
async def volume_balance(interaction: discord.Interaction, left: int,
                         right: int):
    if not (0 <= left <= 100 and 0 <= right <= 100):
        return await interaction.response.send_message(
            "❌ Channel volumes must be between 0 and 100.")

    guild_id_str = str(interaction.guild_id)
    AUDIO_BALANCE[guild_id_str] = (left / 100.0, right / 100.0)

    await interaction.response.send_message(
        f"⚖️ Audio balance set to L: {left}% | R: {right}%\n" +
        "Balance changes would be applied to the audio stream in a full implementation."
    )


@bot.tree.command(name="equalizer",
                  description="Adjust audio equalizer settings")
async def equalizer(interaction: discord.Interaction):
    await interaction.response.send_message(
        "🎛️ Equalizer functionality would allow adjusting different frequency bands in a full implementation.\n"
        +
        "This would use FFmpeg's 'equalizer' audio filter with custom frequency bands."
    )


@bot.tree.command(name="bassboost", description="Toggle bass boost effect")
async def bass_boost(interaction: discord.Interaction):
    guild_id_str = str(interaction.guild_id)

    if guild_id_str not in FILTERS:
        FILTERS[guild_id_str] = []

    if "bassboost" in FILTERS[guild_id_str]:
        FILTERS[guild_id_str].remove("bassboost")
        status = "disabled"
    else:
        FILTERS[guild_id_str].append("bassboost")
        status = "enabled"

    voice_client = interaction.guild.voice_client

    if voice_client and voice_client.is_playing():
        await interaction.response.send_message(
            f"🔊 Bass boost {status}. Effect will apply to the next song.")
    else:
        await interaction.response.send_message(f"🔊 Bass boost {status}.")


@bot.tree.command(
    name="nightcore",
    description="Toggle nightcore effect (increases speed and pitch)")
async def nightcore(interaction: discord.Interaction):
    guild_id_str = str(interaction.guild_id)
    NIGHTCORE_ENABLED[guild_id_str] = not NIGHTCORE_ENABLED.get(
        guild_id_str, False)
    status = "enabled" if NIGHTCORE_ENABLED[guild_id_str] else "disabled"
    await interaction.response.send_message(
        f"🎛️ Nightcore effect {status}. Effect will apply to the next song.")


@bot.tree.command(name="crossfade",
                  description="Enable crossfade between songs")
@app_commands.describe(duration="Crossfade duration in seconds (0 to disable)")
async def crossfade(interaction: discord.Interaction, duration: int):
    if duration < 0:
        return await interaction.response.send_message(
            "❌ Crossfade duration must be positive.")

    await interaction.response.send_message(
        f"🎛️ Crossfade {'enabled with ' + str(duration) + 's duration' if duration > 0 else 'disabled'}.\n"
        +
        "This would smoothly transition between songs in a full implementation."
    )


@bot.tree.command(name="visualize", description="Toggle audio visualization")
async def audio_visualization(interaction: discord.Interaction):
    guild_id_str = str(interaction.guild_id)
    VISUALIZER_ACTIVE[guild_id_str] = not VISUALIZER_ACTIVE.get(
        guild_id_str, False)
    status = "enabled" if VISUALIZER_ACTIVE[guild_id_str] else "disabled"
    await interaction.response.send_message(
        f"📊 Audio visualization {status}.\n" +
        "This would display a visual representation of the audio in a full implementation."
    )


@bot.tree.command(name="createplaylist",
                  description="Create a custom playlist")
@app_commands.describe(name="Name of the playlist")
async def create_playlist(interaction: discord.Interaction, name: str):
    user_id_str = str(interaction.user.id)

    if user_id_str not in CUSTOM_PLAYLISTS:
        CUSTOM_PLAYLISTS[user_id_str] = {}

    if name in CUSTOM_PLAYLISTS[user_id_str]:
        return await interaction.response.send_message(
            f"❌ You already have a playlist named '{name}'.")

    CUSTOM_PLAYLISTS[user_id_str][name] = []
    save_data()
    await interaction.response.send_message(
        f"📝 Created new playlist: **{name}**")


@bot.tree.command(name="addtoplaylist",
                  description="Add current song to a playlist")
@app_commands.describe(playlist_name="Name of your playlist")
async def add_to_playlist(interaction: discord.Interaction,
                          playlist_name: str):
    user_id_str = str(interaction.user.id)
    guild_id_str = str(interaction.guild_id)

    if user_id_str not in CUSTOM_PLAYLISTS:
        return await interaction.response.send_message(
            "❌ You don't have any playlists. Create one first with `/createplaylist`."
        )

    if playlist_name not in CUSTOM_PLAYLISTS[user_id_str]:
        return await interaction.response.send_message(
            f"❌ You don't have a playlist named '{playlist_name}'.")

    if guild_id_str not in CURRENT_TRACKS:
        return await interaction.response.send_message(
            "❌ Nothing is currently playing to add to playlist.")

    current = CURRENT_TRACKS[guild_id_str]
    song_info = {
        "url": current["url"],
        "title": current["title"],
        "duration": current["duration"]
    }

    CUSTOM_PLAYLISTS[user_id_str][playlist_name].append(song_info)
    save_data()
    await interaction.response.send_message(
        f"✅ Added **{current['title']}** to playlist '{playlist_name}'.")


@bot.tree.command(name="playlist",
                  description="Load and play a custom playlist")
@app_commands.describe(playlist_name="Name of the playlist to play")
async def play_playlist(interaction: discord.Interaction, playlist_name: str):
    await interaction.response.defer()

    user_id_str = str(interaction.user.id)
    guild_id_str = str(interaction.guild_id)

    if user_id_str not in CUSTOM_PLAYLISTS:
        return await interaction.followup.send(
            "❌ You don't have any playlists.")

    if playlist_name not in CUSTOM_PLAYLISTS[user_id_str]:
        return await interaction.followup.send(
            f"❌ You don't have a playlist named '{playlist_name}'.")

    if not CUSTOM_PLAYLISTS[user_id_str][playlist_name]:
        return await interaction.followup.send(
            f"❌ Playlist '{playlist_name}' is empty.")

    if not interaction.user.voice:
        return await interaction.followup.send(
            "❌ You must be in a voice channel to play a playlist.")

    voice_channel = interaction.user.voice.channel
    voice_client = interaction.guild.voice_client
    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        if guild_id_str in VOICE_CHANNEL_LOCKS and VOICE_CHANNEL_LOCKS[
                guild_id_str]:
            if voice_client.channel != voice_channel:
                return await interaction.followup.send(
                    "❌ Voice channel is locked.")
        await voice_client.move_to(voice_channel)

    if guild_id_str not in SONG_QUEUES:
        SONG_QUEUES[guild_id_str] = deque()

    playlist = CUSTOM_PLAYLISTS[user_id_str][playlist_name]
    added_count = 0

    for song in playlist:
        SONG_QUEUES[guild_id_str].append(
            (song["url"], song["title"], song["duration"]))
        added_count += 1

    if not voice_client.is_playing() and not voice_client.is_paused():
        await play_next_song(voice_client, interaction.guild_id,
                             interaction.channel)

    await interaction.followup.send(
        f"🎵 Added {added_count} songs from playlist '{playlist_name}' to the queue."
    )


@bot.tree.command(
    name="trackinfo",
    description="Show detailed information about the current track")
async def track_info(interaction: discord.Interaction):
    guild_id_str = str(interaction.guild_id)

    if guild_id_str not in CURRENT_TRACKS:
        return await interaction.response.send_message(
            "❌ Nothing is currently playing.")

    current = CURRENT_TRACKS[guild_id_str]
    elapsed = time.time() - current["started_at"]
    elapsed_str = format_duration(elapsed)
    duration_str = format_duration(
        current["duration"]) if current["duration"] else "Unknown"

    embed = discord.Embed(title="🎵 Track Information",
                          description=f"**{current['title']}**",
                          color=discord.Color.blue())
    embed.add_field(name="Time",
                    value=f"{elapsed_str} / {duration_str}",
                    inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="lyrics",
                  description="Show lyrics for the current song (placeholder)")
async def lyrics(interaction: discord.Interaction):
    guild_id_str = str(interaction.guild_id)

    if guild_id_str not in CURRENT_TRACKS:
        return await interaction.response.send_message(
            "❌ Nothing is currently playing.")

    current = CURRENT_TRACKS[guild_id_str]
    await interaction.response.send_message(
        f"🎵 Lyrics for **{current['title']}**\n\n" +
        "In a full implementation, this would fetch lyrics from a lyrics API or database."
    )


@bot.tree.command(name="search",
                  description="Advanced lyrics search (placeholder)")
@app_commands.describe(query="Lyrics to search for")
async def lyrics_search(interaction: discord.Interaction, query: str):
    await interaction.response.send_message(
        f"🔍 Searching for songs containing: '{query}'\n\n" +
        "In a full implementation, this would search a lyrics database and return matching songs."
    )


@bot.tree.command(name="rate", description="Rate the current song (1-5 stars)")
@app_commands.describe(rating="Rating from 1 to 5 stars")
async def rate_song(interaction: discord.Interaction, rating: int):
    if not 1 <= rating <= 5:
        return await interaction.response.send_message(
            "❌ Rating must be between 1 and 5 stars.")

    guild_id_str = str(interaction.guild_id)
    user_id_str = str(interaction.user.id)

    if guild_id_str not in CURRENT_TRACKS:
        return await interaction.response.send_message(
            "❌ Nothing is currently playing to rate.")

    current = CURRENT_TRACKS[guild_id_str]
    song_id = current.get("url", "")

    if song_id:
        if song_id not in SONG_RATINGS:
            SONG_RATINGS[song_id] = {}

        SONG_RATINGS[song_id][user_id_str] = rating
        save_data()

        ratings = SONG_RATINGS[song_id].values()
        avg_rating = sum(ratings) / len(ratings)
        stars = "⭐" * rating

        await interaction.response.send_message(
            f"Thank you for rating **{current['title']}**!\n" +
            f"Your rating: {stars} ({rating}/5)\n" +
            f"Average rating: {avg_rating:.1f}/5 from {len(ratings)} ratings")
    else:
        await interaction.response.send_message(
            "❌ Could not identify the current song to rate.")


@bot.tree.command(
    name="djmode",
    description="Toggle DJ mode (only authorized users can control music)")
@app_commands.describe(enabled="Enable or disable DJ mode")
async def dj_mode(interaction: discord.Interaction, enabled: bool):
    await interaction.response.send_message(
        f"🎧 DJ Mode {'enabled' if enabled else 'disabled'}.\n" +
        "In a full implementation, this would restrict music control to users with a DJ role."
    )


@bot.tree.command(name="game", description="Start a music guessing game")
async def music_game(interaction: discord.Interaction):
    guild_id_str = str(interaction.guild_id)

    if guild_id_str in ACTIVE_GAME_SESSIONS:
        return await interaction.response.send_message(
            "❌ A music game is already in progress.")

    await interaction.response.send_message(
        "🎮 Music guessing game!\n\n" +
        "In a full implementation, this would play short clips of songs and users would guess the title/artist."
    )

    ACTIVE_GAME_SESSIONS[guild_id_str] = {
        "active": True,
        "started_by": interaction.user.id
    }


@bot.tree.command(name="join", description="Join your voice channel")
async def join(interaction: discord.Interaction):
    if not interaction.user.voice:
        return await interaction.response.send_message(
            "❌ You must be in a voice channel first.")

    voice_channel = interaction.user.voice.channel
    guild_id_str = str(interaction.guild_id)

    if guild_id_str in VOICE_CHANNEL_LOCKS and VOICE_CHANNEL_LOCKS[
            guild_id_str]:
        if interaction.guild.voice_client and interaction.guild.voice_client.channel != voice_channel:
            return await interaction.response.send_message(
                "❌ Voice channel is locked. Cannot join your channel.")

    try:
        if interaction.guild.voice_client is None:
            await voice_channel.connect()
        else:
            await interaction.guild.voice_client.move_to(voice_channel)

        await interaction.response.send_message(
            f"✅ Joined {voice_channel.mention}")
    except Exception as e:
        await interaction.response.send_message(
            f"❌ Error joining voice channel: {str(e)}")


@bot.tree.command(name="leave", description="Leave the voice channel")
async def leave(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client
    if voice_client is None:
        return await interaction.response.send_message(
            "❌ I'm not in a voice channel.")

    guild_id_str = str(interaction.guild_id)
    if guild_id_str in SONG_QUEUES:
        SONG_QUEUES[guild_id_str].clear()

    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    await voice_client.disconnect()
    await interaction.response.send_message("👋 Left the voice channel.")


@bot.tree.command(name="lock",
                  description="Lock the bot to the current voice channel")
@app_commands.describe(enabled="Enable or disable voice channel lock")
async def lock_channel(interaction: discord.Interaction, enabled: bool):
    guild_id_str = str(interaction.guild_id)
    voice_client = interaction.guild.voice_client

    if enabled and not voice_client:
        return await interaction.response.send_message(
            "❌ I'm not in a voice channel to lock.")

    VOICE_CHANNEL_LOCKS[guild_id_str] = enabled
    save_data()

    if enabled:
        channel_name = voice_client.channel.name
        await interaction.response.send_message(
            f"🔒 Locked to voice channel '{channel_name}'.")
    else:
        await interaction.response.send_message(
            "🔓 Voice channel lock disabled.")


@bot.tree.command(
    name="autojoin",
    description="Set bot to automatically join your voice channel")
@app_commands.describe(enabled="Enable or disable auto-join")
async def auto_join(interaction: discord.Interaction, enabled: bool):
    user_id_str = str(interaction.user.id)
    guild_id_str = str(interaction.guild_id)

    if enabled:
        if not interaction.user.voice:
            return await interaction.response.send_message(
                "❌ You must be in a voice channel to enable auto-join.")

        voice_channel_id = str(interaction.user.voice.channel.id)

        if user_id_str not in AUTO_JOIN_CHANNELS:
            AUTO_JOIN_CHANNELS[user_id_str] = {}

        AUTO_JOIN_CHANNELS[user_id_str][guild_id_str] = voice_channel_id
        channel_name = interaction.user.voice.channel.name

        await interaction.response.send_message(
            f"🔄 Auto-join enabled for channel '{channel_name}'.")
    else:
        if user_id_str in AUTO_JOIN_CHANNELS and guild_id_str in AUTO_JOIN_CHANNELS[
                user_id_str]:
            del AUTO_JOIN_CHANNELS[user_id_str][guild_id_str]

            if not AUTO_JOIN_CHANNELS[user_id_str]:
                del AUTO_JOIN_CHANNELS[user_id_str]

            await interaction.response.send_message("🛑 Auto-join disabled.")
        else:
            await interaction.response.send_message(
                "❌ You don't have auto-join enabled.")

    save_data()


@bot.tree.command(
    name="filters",
    description="Apply audio filters to enhance your music experience")
@app_commands.describe(filter_name="The audio filter to toggle")
@app_commands.choices(filter_name=[
    app_commands.Choice(name="Bass Boost", value="bassboost"),
    app_commands.Choice(name="Nightcore", value="nightcore"),
    app_commands.Choice(name="8D Audio", value="8d"),
    app_commands.Choice(name="Vaporwave", value="vaporwave"),
    app_commands.Choice(name="Tremolo", value="tremolo"),
    app_commands.Choice(name="Vibrato", value="vibrato"),
    app_commands.Choice(name="Reverse", value="reverse"),
    app_commands.Choice(name="Normalizer", value="normalizer"),
    app_commands.Choice(name="Echo", value="echo")
])
async def filters(interaction: discord.Interaction, filter_name: str):
    guild_id_str = str(interaction.guild_id)

    if guild_id_str not in FILTERS:
        FILTERS[guild_id_str] = []

    if filter_name in FILTERS[guild_id_str]:
        FILTERS[guild_id_str].remove(filter_name)
        status = "disabled"
    else:
        FILTERS[guild_id_str].append(filter_name)
        status = "enabled"

    embed = discord.Embed(title="🎛️ Audio Filters",
                          description=f"**{filter_name}** filter {status}",
                          color=discord.Color.blue())

    active_filters = FILTERS[guild_id_str]
    if active_filters:
        embed.add_field(name="Active Filters",
                        value=", ".join(active_filters),
                        inline=False)
    else:
        embed.add_field(name="Active Filters", value="None", inline=False)

    embed.set_footer(
        text=
        "Filters will apply to new songs. Some filters may increase CPU usage."
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="language", description="Set your preferred language")
@app_commands.describe(language_code="Language code")
@app_commands.choices(language_code=[
    app_commands.Choice(name="English", value="en"),
    app_commands.Choice(name="Spanish", value="es"),
    app_commands.Choice(name="French", value="fr"),
    app_commands.Choice(name="German", value="de"),
    app_commands.Choice(name="Italian", value="it"),
    app_commands.Choice(name="Portuguese", value="pt"),
    app_commands.Choice(name="Russian", value="ru"),
    app_commands.Choice(name="Japanese", value="ja"),
    app_commands.Choice(name="Korean", value="ko"),
    app_commands.Choice(name="Chinese", value="zh"),
    app_commands.Choice(name="Dutch", value="nl")
])
async def set_language(interaction: discord.Interaction, language_code: str):
    user_id_str = str(interaction.user.id)
    LANGUAGE_PREFERENCES[user_id_str] = language_code
    save_data()
    language_name = SUPPORTED_LANGUAGES.get(language_code, "Unknown")
    await interaction.response.send_message(
        f"🌐 Language preference set to {language_name}.")


@bot.tree.command(name="audioquality",
                  description="Set audio quality for playback")
@app_commands.describe(quality="Audio quality level")
@app_commands.choices(quality=[
    app_commands.Choice(name="Low (64kbps)", value="64"),
    app_commands.Choice(name="Medium (128kbps)", value="128"),
    app_commands.Choice(name="High (192kbps)", value="192"),
    app_commands.Choice(name="Very High (256kbps)", value="256")
])
async def audio_quality(interaction: discord.Interaction, quality: str):
    await interaction.response.send_message(
        f"🎚️ Audio quality set to {quality}kbps.\n" +
        "In a full implementation, this would adjust the YT-DLP format selection."
    )


@bot.tree.command(name="help",
                  description="Show all available commands and their usage")
async def help_command(interaction: discord.Interaction):
    """Display an embed with all available commands categorized by functionality"""

    embed = discord.Embed(title="🎵 Music Bot Help",
                          description="Here are all the available commands:",
                          color=discord.Color.blue())

    playback_commands = """
    ▶️ **/play** `<song_query>` - Play a song or add to queue
    ⏸️ **/pause** - Pause current song
    ▶️ **/resume** - Resume playback
    ⏹️ **/stop** - Stop playback and clear queue
    ⏭️ **/skip** - Skip current song
    ⏮️ **/rewind** - Restart current song
    🔍 **/seek** `<position>` - Seek to position (mm:ss)
    🔁 **/repeat** - Toggle repeat for current song
    🔀 **/shuffle** - Shuffle the queue
    ⏭️ **/playnext** `<song>` - Add song to front of queue
    ↗️ **/skipto** `<position>` - Skip to specific queue position
    """
    embed.add_field(name="🎶 Playback Controls",
                    value=playback_commands,
                    inline=False)

    queue_commands = """
    📋 **/queue** - Show current queue
    🧹 **/clearqueue** - Clear the queue
    ⏱️ **/queuetime** - Show estimated queue duration
    🎵 **/nowplaying** - Show current track info
    ℹ️ **/trackinfo** - Detailed track information
    """
    embed.add_field(name="📑 Queue Management",
                    value=queue_commands,
                    inline=False)

    audio_commands = """
    🔊 **/volume** `<1-100>` - Set volume level
    🎚️ **/volumelimiter** `<on/off>` - Toggle volume limiter
    ⚖️ **/balance** `<left> <right>` - Set audio balance
    🎛️ **/equalizer** - Adjust equalizer settings
    🎚️ **/filters** `<filter>` - Apply audio filters
    🎸 **/bassboost** - Toggle bass boost
    🌙 **/nightcore** - Toggle nightcore effect
    🎧 **/audioquality** `<quality>` - Set audio quality
    """
    embed.add_field(name="🎛️ Audio Control",
                    value=audio_commands,
                    inline=False)

    playlist_commands = """
    📝 **/createplaylist** `<name>` - Create new playlist
    ➕ **/addtoplaylist** `<playlist>` - Add current song
    🎼 **/playlist** `<name>` - Play a saved playlist
    """
    embed.add_field(name="🎼 Playlists", value=playlist_commands, inline=False)

    voice_commands = """
    🎤 **/join** - Join your voice channel
    🚪 **/leave** - Leave voice channel
    🔒 **/lock** `<on/off>` - Lock to current channel
    🤖 **/autojoin** `<on/off>` - Auto-join your channel
    """
    embed.add_field(name="🔊 Voice Channel", value=voice_commands, inline=False)

    fun_commands = """
    📜 **/lyrics** - Show lyrics for current song
    ⭐ **/rate** `<1-5>` - Rate current song
    🎮 **/game** - Start music guessing game
    """
    embed.add_field(name="🎮 Fun & Games", value=fun_commands, inline=False)

    settings_commands = """
    🌐 **/language** `<code>` - Set preferred language
    🎧 **/djmode** `<on/off>` - Toggle DJ mode
    """
    embed.add_field(name="⚙️ Settings", value=settings_commands, inline=False)

    embed.set_footer(text="Use slash commands (/) before each command")
    await interaction.response.send_message(embed=embed)


if __name__ == "__main__":
    bot.run(TOKEN)
