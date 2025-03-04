import discord
from discord.ext import commands
import yt_dlp
from dotenv import load_dotenv
import os
import asyncio
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import speech_recognition as sr
from textblob import TextBlob
import json
import requests
from openai import OpenAI
from datetime import datetime, timezone, timedelta
import lyricsgenius
import time
from gtts import gTTS
from pydub.playback import play
from pydub import AudioSegment

# Load champions data from a JSON file
with open('data.json', 'r') as json_file:
    champions = json.load(json_file)

load_dotenv()

TOKEN = os.getenv("KUDJ_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
GIPHY_API_KEY = os.getenv("GIPHY_API_KEY")
RIOT_API_KEY = os.getenv("RIOT_API_KEY")
GENIUS_ACCESS_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
IMGFLIP_USERNAME = os.getenv("IMGFLIP_USERNAME")
IMGFLIP_PASSWORD = os.getenv("IMGFLIP_PASSWORD")

client= OpenAI(
    api_key= OPENAI_API_KEY
)

if not os.path.exists('downloads'):
    os.makedirs('downloads')

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="@", intents=intents)

FFMPEG_OPTIONS = {
    'options': '-vn'
}

queues = {}
currently_playing = {}  # Track the currently playing song for each guild
is_playing = {}  # Track if the bot is currently playing a song for each guild

def get_queue(guild_id):
    """Returns the queue for a specific guild."""
    if guild_id not in queues:
        queues[guild_id] = []
    return queues[guild_id]

def get_champion_by_id(champion_id):
    for champ_name, champ_data in champions["data"].items():
        if champ_data["key"] == str(champion_id):
            return champ_name
    return None 

def get_latest_version() -> str:
    versions_url = "https://ddragon.leagueoflegends.com/api/versions.json"
    response = requests.get(versions_url).json()
    if not response:
        return None
    return response[0]

@bot.event
async def on_ready():
    print(f'✅ Logged in as {bot.user}')

@bot.command()
async def join(ctx):
    """Command to make the bot join a voice channel."""
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        if ctx.voice_client:
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        await ctx.send("🎶 Joined the voice channel!")
    else:
        await ctx.send("❌ You need to be in a voice channel to use this command.")

async def play_audio(ctx, query):
    """Plays audio from a YouTube link or search query."""
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("❌ You need to be in a voice channel to use this command.")
            return

    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'noplaylist': True,  
        'geo_bypass': True,  
        'default_search': 'ytsearch', 
        'outtmpl': 'downloads/%(title)s.%(ext)s',  
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(query, download=False)
            
            if 'entries' in info_dict:
                info = info_dict['entries'][0]
            else:
                info = info_dict
                
            title = info.get('title', 'Unknown Title')
            sanitized_title = ''.join(c for c in title if c.isalnum() or c in ' -_').strip()
            
            download_info = ydl.extract_info(info['webpage_url'], download=True)
            
            file_path = ydl.prepare_filename(download_info)
            base_path = os.path.splitext(file_path)[0]  
            
            file_path = f"{base_path}.mp3"
            
            print(f"Expected file path: {file_path}")

            if not os.path.exists(file_path):
                for ext in ['.mp3', '.m4a', '.webm', '.opus']:
                    test_path = f"{base_path}{ext}"
                    print(f"Checking for: {test_path}")
                    if os.path.exists(test_path):
                        file_path = test_path
                        print(f"Found file at: {file_path}")
                        break
                else:
                    print("Files in downloads directory:")
                    for f in os.listdir('downloads'):
                        print(f" - {f}")
                    await ctx.send(f"❌ Could not find the downloaded audio file for '{title}'.")
                    return

        queue = get_queue(ctx.guild.id)
        queue.append((file_path, title))
        await ctx.send(f'🎵 Added to queue: **{title}**')

        if not ctx.voice_client.is_playing():
            await play_next(ctx)

    except Exception as e:
        print(f"Error in play_audio: {str(e)}")
        await ctx.send(f"⚠️ Error: {str(e)}")

async def play_next(ctx):
    """Plays the next song in the queue."""
    guild_id = ctx.guild.id
    queue = get_queue(guild_id)
    
    if queue:
        # Get the next song and remove it from the queue
        file_path, title = queue.pop(0)
        
        if not os.path.exists(file_path):
            await ctx.send(f"❌ Could not find the file for '{title}'. Skipping to next song.")
            await play_next(ctx)
            return
            
        try:
            # Track the currently playing song
            currently_playing[guild_id] = (file_path, title)
            is_playing[guild_id] = True
            
            # Define the callback for when the song finishes
            def after_playing(error):
                # When a song ends, play the next song
                if error:
                    print(f"Error in after_playing: {error}")
                is_playing[guild_id] = False
                asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
            
            # Play the song
            ctx.voice_client.play(discord.FFmpegPCMAudio(file_path, **FFMPEG_OPTIONS), after=after_playing)
            await ctx.send(f'▶️ Now playing: **{title}**')
            
        except Exception as e:
            await ctx.send(f"⚠️ Error playing '{title}': {str(e)}")
            # If there's an error, try to play the next song
            is_playing[guild_id] = False
            asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop)
    else:
        # If the queue is empty
        currently_playing[guild_id] = None
        is_playing[guild_id] = False
        await ctx.send("🎶 Queue is empty. Add more songs with `!play`")

@bot.command()
async def play(ctx, *, query: str):
    """Plays audio from a YouTube link, Spotify link, or a search query."""
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("❌ You need to be in a voice channel to use this command.")
            return

    if "open.spotify.com" in query:
        if "track" in query:
            track_id = query.split("track/")[1].split("?")[0]
            track_info = sp.track(track_id)
            track_name = track_info['name']
            artist_name = track_info['artists'][0]['name']
            search_query = f"{track_name} {artist_name}"
            await ctx.send(f'🔍 Searching YouTube for: **{track_name} by {artist_name}**')
            await play_audio(ctx, search_query)
        else:
            await ctx.send("❌ Only Spotify track links are supported.")
    else:
        await ctx.send(f'🔍 Searching for: **{query}**')
        await play_audio(ctx, query)

# @bot.command()
# async def sing(ctx, *, song_title_artist_name: str):
#     if not ctx.voice_client:
#         if ctx.author.voice:
#             await ctx.author.voice.channel.connect()
#         else:
#             await ctx.send("❌ You need to be in a voice channel to use this command.")
#             return
    
#     try:
#         song_title, artist_name = song_title_artist_name.split(" ", 1)
#     except ValueError:
#         await ctx.send("❌ Song's title and Artist's name not recognized.")
#         return
    
#     max_retries = 3
#     genius = lyricsgenius.Genius(GENIUS_ACCESS_TOKEN, timeout=15)

#     song_lyrics = ""
#     if not artist_name:
#         artist_name = ""

#     for attempt in range(max_retries):
#         try:
#             song = genius.search_song(song_title, artist_name)

#             song_title = song.title
#             artist_name = song.artist

#             if not song:
#                 await ctx.send(f"❌ No results found for {song_title} by {artist_name}")
#                 return
#             else:
#                 song_lyrics += song.lyrics
#                 break
#         except requests.exceptions.Timeout:
#             await ctx.send(f"❌ Requests timed out. Retrying ({attempt + 1}/{max_retries})...")
#             time.sleep(5)
#         except Exception as e:
#             await ctx.send(f"Error fetching lyrics for {song_title} by {artist_name}")
#             return

#     tts = gTTS(text=song_lyrics, lang="en")
#     tts.save(f"downloads/AI {song_title}.mp3")
#     queue = get_queue(ctx.guild.id)
#     queue.append((f"downloads/AI {song_title}.mp3", f"AI {song_title}"))
#     if not ctx.voice_client.is_playing():
#         await play_next(ctx)
#     else:
#         await ctx.send("🎶 Added the song to the queue.")


@bot.command()
async def listen(ctx):
    if not ctx.voice_client:
        if ctx.author.voice:
            await ctx.author.voice.channel.connect()
        else:
            await ctx.send("❌ You need to be in a voice channel to use this command.")
            return
    
    recognizer = sr.Recognizer()
    microphone = sr.Microphone()

    await ctx.send("🎤 Listening... Say the name of the song you want to play.")
    with microphone as source:
        try:
            recognizer.adjust_for_ambient_noise(source)
            audio = recognizer.listen(source, timeout=10)

            query = recognizer.recognize_google(audio)
            await ctx.send(f'🎤 You said: **{query}**')

            await play_audio(ctx, query)        
        except sr.UnknownValueError:
            await ctx.send("❌ I couldn't understand what you said.")
        except sr.RequestError as e:
            await ctx.send(f"⚠️ Error with the speech recognition service: {str(e)}")
        except Exception as e:
            await ctx.send(f"⚠️ Error: {str(e)}")

@bot.command()
async def sense(ctx):
    if not ctx.voice_client:
        if ctx.author.voice:
            ctx.author.voice.channel.connect()
        else:
            await ctx.send("❌ You need to be in a voice channel to use this command.")
            return
    
    recognizer = sr.Recognizer()
    microphone = sr.Microphone()

    await ctx.send("🎤 Listening... Tell me how you're feeling.")   

    with microphone as source:
        try: 
            recognizer.adjust_for_ambient_noise(source)
            audio = recognizer.listen(source)
            
            text = recognizer.recognize_google(audio)
            await ctx.send(f'🎤 You said: **{text}**')

            analysis = TextBlob(text)
            sentiment = analysis.sentiment.polarity

            if sentiment > 0.2:
                mood = "happy"
                query = "upbeat happy music"
            elif sentiment < -0.2:
                mood = "sad"
                query = "calm acoustic music"
            else:
                mood = "neutral"
                query = "lo-fi chill music"

            await ctx.send(f'🎭 Detected mood: **{mood}**. Playing a song to match your mood...')

            # Play a song based on the mood
            await play_audio(ctx, query)

        except sr.UnknownValueError:
            await ctx.send("❌ I couldn't understand what you said.")
        except sr.RequestError as e:
            await ctx.send(f"⚠️ Error with the speech recognition service: {str(e)}")
        except Exception as e:
            await ctx.send(f"⚠️ Error: {str(e)}")

@bot.command()
async def saturday(ctx):
    if not ctx.voice_client:
        if ctx.author.voice:
            ctx.author.voice.channel.connect()
        else:
            await ctx.send("❌ You need to be in a voice channel to use this command.")
            return
    
    url = "https://www.youtube.com/watch?v=fXpJlk0sTGU"

    queue = get_queue(ctx.guild.id)

    if not queue:
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
            await ctx.send("⏭️ Skipped the current song.")
            await play_audio(ctx, url)
        else:
            await play_audio(ctx, url)
    else:
        ydl_opts = {
            'format': 'bestaudio/best',
            'quiet': True,
            'noplaylist': True,  
            'geo_bypass': True,  
            'default_search': 'ytsearch', 
            'outtmpl': 'downloads/%(title)s.%(ext)s',  
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }

        try: 
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info_dict = ydl.extract_info(url, download=False)

                if 'entries' in info_dict:
                    info = info_dict['entries'][0]
                else:
                    info = info_dict
                
                title = info.get('title', 'Unknown Title')
                
                download_info = ydl.extract_info(info['webpage_url'], download=True)

                file_path = ydl.prepare_filename(download_info)
                base_path = os.path.splitext(file_path)[0]

                file_path = f"{base_path}.mp3"

                print(f"Expected file path: {file_path}")

                if not os.path.exists(file_path):
                    for ext in ['.mp3', '.m4a', '.webm', '.opus']:
                        test_path = f"{base_path}{ext}"
                        print(f"Checking for: {test_path}")
                        if os.path.exists(test_path):
                            file_path = test_path
                            print(f"Found file at: {file_path}")
                            break
                    else:
                        print("Files in downloads directory:")
                        for f in os.listdir('downloads'):
                            print(f" - {f}")
                        await ctx.send(f"❌ Could not find the downloaded audio file for '{title}'.")
                        return
            
            queue.insert(0, (file_path, title))
            ctx.voice_client.stop()
            await ctx.send("⏭️ Skipped the current song.")
        except Exception as e:
            print(f"Error in play_audio: {str(e)}")
            await ctx.send(f"⚠️ Error: {str(e)}")


@bot.command()
async def skip(ctx):
    """Skips the current song and plays the next one in the queue."""
    if ctx.voice_client and ctx.voice_client.is_playing():
        ctx.voice_client.stop()
        await ctx.send("⏭️ Skipped the current song.")
        
    else:
        await ctx.send("❌ No song is currently playing.")

@bot.command()
async def queue(ctx):
    """Displays the current queue."""
    guild_id = ctx.guild.id
    queue = get_queue(guild_id)
    
    # Start with the currently playing song if there is one
    if guild_id in currently_playing and currently_playing[guild_id]:
        response = "🎶 Currently playing:\n"
        response += f"▶️ {currently_playing[guild_id][1]}\n\n"
    else:
        response = "🎶 No song currently playing.\n\n"
    
    if queue:
        response += "🎶 Up next:\n"
        queue_list = "\n".join([f"{i+1}. {title}" for i, (_, title) in enumerate(queue)])
        response += queue_list
        await ctx.send(response)
    else:
        response += "🎶 The queue is empty. Add more songs with `!play`"
        await ctx.send(response)

@bot.command()
async def build(ctx, *, query: str):
    champion = query.lower().replace(" ", "")
    build_url = f"https://u.gg/lol/champions/{champion}/build"
    embed = discord.Embed(title=f"🔧 Best Build for {query.lower().capitalize()}", color=discord.Color.blue(), url=build_url)
    embed.set_footer(text="Click the title for details.")

    await ctx.send(embed=embed)

@bot.command()
async def rank(ctx, *, game_name_tag_line: str):
    try:
        game_name, tag_line = game_name_tag_line.split("#", 1)
    except ValueError:
        await ctx.send("❌ Please provide both a game name and a tagline.")
        return
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    get_account_url = f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    get_account_response = requests.get(get_account_url, headers=headers).json()
    if "status" in get_account_response:
        await ctx.send("❌ Incorrect credentials. Try a different Game Name or Tagline")
        return
    puuid = get_account_response["puuid"]
    summoner_id_url = f"https://na1.api.riotgames.com/lol/summoner/v4/summoners/by-puuid/{puuid}"
    summoner_id_response = requests.get(summoner_id_url, headers=headers).json()
    if "status" in summoner_id_response:
        await ctx.send("❌ Error getting the Summoner's ID.")
        return
    summoner_id = summoner_id_response["id"]
    summoner_rank_url = f"https://na1.api.riotgames.com/lol/league/v4/entries/by-summoner/{summoner_id}"
    summoner_rank_response = requests.get(summoner_rank_url, headers=headers).json()
    if "status" in summoner_rank_response:
        await ctx.send(f"❌ Error getting the rank of Player {game_name}")
        return
    message = "\n".join(f'{index + 1}. {summoner_rank["queueType"]} // Rank: {summoner_rank["tier"]} {summoner_rank["rank"]} // LP: {summoner_rank["leaguePoints"]}/100 // W/R: {summoner_rank["wins"]}/{summoner_rank["losses"]}' for index, summoner_rank in enumerate(summoner_rank_response))
    await ctx.send(message)

@bot.command()
async def mastery(ctx, *, game_name_tag_line: str):
    try:
        game_name, tag_line = game_name_tag_line.split("#", 1)
    except ValueError:
        await ctx.send("❌ Please provide both a game name and a tagline.")
        return
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    get_account_url = f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    get_account_response = requests.get(get_account_url, headers=headers).json()
    if "status" in get_account_response:
        await ctx.send("❌ Incorrect credentials. Try a different Game Name or Tagline")
        return
    puuid = get_account_response["puuid"]
    get_masteries_url = f"https://na1.api.riotgames.com/lol/champion-mastery/v4/champion-masteries/by-puuid/{puuid}"
    get_masteries_response = requests.get(get_masteries_url, headers=headers).json()
    champions_list = get_masteries_response[:5]
    mastery_list = []
    for i in range(len(champions_list)):
        champion_id = int(champions_list[i]["championId"])
        champ_name = get_champion_by_id(champion_id)
        mastery_list.append((champ_name, champions_list[i]["championLevel"], champions_list[i]["championPoints"]))
    if not mastery_list:
        await ctx.send("❌ No mastery data found for the provided Game Name and Tagline.")
        return
    
    mastery_message = "\n".join(f"{index + 1}. {mastery_champ[0]} // championLevel: {mastery_champ[1]} // championPoints: {mastery_champ[2]}" for index, mastery_champ in enumerate(mastery_list))
    await ctx.send(mastery_message)

@bot.command()
async def history(ctx, *, game_name_tag_line: str):
    try:
        game_name, tag_line = game_name_tag_line.split("#", 1)
    except ValueError:
        await ctx.send("❌ Please provide both a game name and a tagline.")
        return
    headers = {"X-Riot-Token": RIOT_API_KEY}
    
    get_account_url = f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    get_account_response = requests.get(get_account_url, headers=headers).json()
    if "status" in get_account_response:
        await ctx.send("❌ Incorrect credentials. Try a different Game Name or Tagline")
        return
    puuid = get_account_response["puuid"]
    match_history_url = f"https://americas.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids"
    match_history_response = requests.get(match_history_url, headers=headers).json()
    if not match_history_response:
        await ctx.send(f"❌ Error getting match history of {game_name}")
        return
    match_ids = match_history_response[:5]
    match_history = []
    for match_id in match_ids:
        url = f"https://americas.api.riotgames.com/lol/match/v5/matches/{match_id}"
        response = requests.get(url, headers=headers).json()
        if not response:
            await ctx.send(f"❌ Error getting info of match with ID: {match_id}")
            return
        timestamp = response["info"]["gameCreation"]
        timestamp = datetime.fromtimestamp(timestamp / 1000, timezone.utc).astimezone(timezone(timedelta(hours=-6))).strftime('%Y-%m-%d %H:%M:%S')
        game_mode = response["info"]["gameMode"]
        for _, player_info in enumerate(response["info"]["participants"]):
            if player_info["puuid"] == puuid:
                match_history.append({
                    "timestamp": timestamp,
                    "game_mode": game_mode,
                    "champion": player_info["championName"],
                    "kills": player_info["kills"],
                    "deaths": player_info["deaths"],
                    "assists": player_info["assists"],
                    "win": player_info["win"]
                })
    if not match_history:
        await ctx.send(f"❌ Error getting the match history of player {game_name}.")
        return
    
    message = "\n".join(f'{index + 1}. {match_info["timestamp"]} // {match_info["game_mode"]} // {match_info["champion"]} // KDA: {match_info["kills"]}/{match_info["deaths"]}/{match_info["assists"]} // {"Victory" if match_info["win"] else "Defeat"}' for index, match_info in enumerate(match_history))
    await ctx.send("RECENT GAMES (LAST 5 PLAYED):\n" + message)

@bot.command()
async def champion(ctx, *, champion: str):
    if " " in champion:
        if champion.lower() != "jarvan iv":
            first_word, second_word = champion.split(" ", 1)
            champion = first_word.lower().capitalize() + second_word.lower().capitalize()
        else:
            first_word, second_word = champion.split(" ", 1)
            champion = first_word.lower().capitalize() + second_word.upper()
    else:
        champion = champion.lower().capitalize()
    latest_version = get_latest_version()
    if not latest_version:
        await ctx.send("❌ Error getting the latest version of League of Legends.")
        return
    champ_icon_url = f"https://ddragon.leagueoflegends.com/cdn/{latest_version}/img/champion/{champion}.png"
    champ_icon_response = requests.get(champ_icon_url)
    if champ_icon_response.status_code != 200:
        await ctx.send(f"❌ Error getting the icon of {champion}.")
        return
    embed = discord.Embed(title=f"Champion: {champion}", color=discord.Color.blue())
    embed.set_image(url=champ_icon_url)
    embed.add_field(name="Winrate", value="50%", inline=False)
    embed.add_field(name="Items", value="[Infinity Edge](champ_icon_url)", inline=False)
    embed.add_field(name="Skill Order", value="Q -> E -> W -> R", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def spectate(ctx, *, game_name_tag_line: str):
    """Spectate a live game from a player"""
    try:
        game_name, tag_line= game_name_tag_line.split("#", 1)
    except ValueError:
        await ctx.send("❌ Please provide both game name and tag line of the player you want to spectate.")
        return
    
    headers= {
        "X-Riot-Token": RIOT_API_KEY
    }
    
    get_account_url = f"https://americas.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
    get_account_response = requests.get(get_account_url, headers=headers).json()
    
    if not get_account_response or "status" in get_account_response:
        await ctx.send(f"❌ Failed fetching for the puuID of {game_name}")
        return
    puuid = get_account_response["puuid"]
    spectate_url = f"https://na1.api.riotgames.com/lol/spectator/v5/active-games/by-summoner/{puuid}"
    spectate_response = requests.get(spectate_url, headers=headers)
    if not spectate_response or spectate_response.status_code != 200:
        await ctx.send("❌ Unable to retrieve match data. The player may not be currently engaged in a game.")
        return
    spectate_data = spectate_response.json()
    game_mode = spectate_data["gameMode"]
    participants = spectate_data["participants"]
    members_per_team = int(len(participants) / 2) 
    champs = []
    for i in range(members_per_team):
        champ1_id = participants[i]["championId"]
        champ2_id = participants[i + members_per_team]["championId"]
        player1_riot_id = participants[i]["riotId"] 
        player2_riot_id = participants[i + members_per_team]["riotId"]
        champ1_name = get_champion_by_id(champ1_id)
        champ2_name = get_champion_by_id(champ2_id)
        champs.append((
            {
                "player_riot_id": player1_riot_id,
                "champ_name": champ1_name
            }, 
            {
                "player_riot_id": player2_riot_id,
                "champ_name": champ2_name
            }
        ))

    if not champs:
        await ctx.send(f"❌ No champions found for the provided player {game_name}.")

    message = f"**{game_mode}**\n"
    for champ_pair in champs:
        message += f"Player: {champ_pair[0]['player_riot_id']}  Champion: {champ_pair[0]['champ_name']}        Player: {champ_pair[1]['player_riot_id']}  Champion: {champ_pair[1]['champ_name']}\n"
    await ctx.send(message)
    


@bot.command()
async def gif(ctx, *, keyword: str):
    giphy_url = f"https://api.giphy.com/v1/gifs/search?api_key={GIPHY_API_KEY}&q={keyword}&limit=10&rating=g"
    response = requests.get(giphy_url).json()
    if response['data']:
        gif_url = response['data'][0]['images']['original']['url']
        await ctx.send(gif_url)
    else:
        await ctx.send("No GIFs found for that keyword!")

@bot.command()
async def coach(ctx, *, message: str):
    if ctx.author.voice:
        if ctx.voice_client:
            await ctx.voice_client.move_to(ctx.author.voice.channel)
        else:
            await ctx.author.voice.channel.connect()
            await ctx.send("🎶 Joined the voice channel!")
    else:
        await ctx.send("❌ You need to be in a voice channel to use this command.")

    query = f"Act like you are a League of Legends coach for a team that is currently playing in a very important match, fighting for the chance to lift the tropy. Give us some coaching advice based on the current situation that we are in, which is provided by this message: {message}.Make it cohesive and coherent with around 50 words"
    completion = client.chat.completions.create(
        model="gpt-4o-mini",
        store=True,
        messages=[
            {
                "role": "user",
                "content": query
            }
        ]
    )
    # await ctx.send(f"{completion.choices[0].message.content}")
    cleaned_title = ''.join(c for c in completion.choices[0].message.content[:30] if c.isalnum() or c in ' -_').strip()
    tts = gTTS(text=completion.choices[0].message.content, lang="en")
    tts.save(f"downloads/{cleaned_title}.mp3")
    queue = get_queue(ctx.guild.id)
    queue.append((f"downloads/{cleaned_title}.mp3", cleaned_title))
    if not ctx.voice_client.is_playing():
        await play_next(ctx)
    else:
        await ctx.send("🎶 Added the speech to the queue")

@bot.command()
async def get_meme(ctx):
    """Get a list of top 20 available memes"""
    meme_url = "https://api.imgflip.com/get_memes"
    response = requests.get(meme_url).json()
    if not response:
        await ctx.send("❌ Failed getting the list of top 20 available memes.")
        return
    if "success" in response and response["success"]:
        meme_list = response["data"]["memes"]
    text = "\n".join(f'{index + 1}. {meme["name"]} // ID: {meme["id"]}' for index, meme in enumerate(meme_list[:20]))
    await ctx.send("List of available memes:\n" + text)

@bot.command()
async def create_meme(ctx, *, text0_text1_template_id: str):
    try:
        text0, text1, template_id = text0_text1_template_id.split("|", 2)
    except ValueError:
        await ctx.send("❌ Please provide content for all meme boxes and the meme's ID.")
        return
    
    create_meme_url = "https://api.imgflip.com/caption_image"
    params = {
        "template_id": template_id,
        "username": IMGFLIP_USERNAME,
        "password": IMGFLIP_PASSWORD,
        "text0": text0,
        "text1": text1
    }
    response = requests.post(create_meme_url, params=params).json()
    if not response:
        await ctx.send("❌ Failed creating the meme.")
        return
    elif "success" in response and response["success"]:
        await ctx.send(response["data"]["url"])
    

@bot.command()
async def leave(ctx):
    """Command to make the bot leave the voice channel."""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Left the voice channel.")
        if ctx.guild.id in queues:
            del queues[ctx.guild.id]
        if ctx.guild.id in currently_playing:
            del currently_playing[ctx.guild.id]
        if ctx.guild.id in is_playing:
            del is_playing[ctx.guild.id]
    else:
        await ctx.send("❌ I'm not in a voice channel.")

@bot.event
async def on_voice_state_update(member, before, after):
    """Cleans up downloaded files when the bot leaves a voice channel."""
    if member == bot.user and after.channel is None:
        for file in os.listdir('downloads'):
            file_path = os.path.join('downloads', file)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"⚠️ Error deleting file {file_path}: {e}")

bot.run(TOKEN)