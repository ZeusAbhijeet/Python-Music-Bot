import logging
from typing import Optional

import hikari
import lightbulb
import lavasnek_rs
import spotipy
import re
import lyricsgenius
import urllib.parse as urlparse
from spotipy.oauth2 import SpotifyClientCredentials
from consts import LAVALINK_PASSWORD, PREFIX, TOKEN, SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, GENIUS_ACCESS_TOKEN
from lightbulb.utils import pag, nav
from lightbulb.ext import neon

# If True connect to voice with the hikari gateway instead of lavasnek_rs's
HIKARI_VOICE = False

URL_REGEX = r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2,4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+(?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\".,<>?«»“”‘’]))"
TIME_REGEX = r"([0-9]{1,2})[:ms](([0-9]{1,2})s?)?"

#TextChannel : dict

class EventHandler:
    """Events from the Lavalink server"""

    async def track_start(self, lavalink: lavasnek_rs.Lavalink, event: lavasnek_rs.TrackStart) -> None:
        logging.info("Track started on guild: %s", event.guild_id)

        # If your bot is going to be in multiple servers, I recommend removing the following code.
        # Since my bot is going to be used in just one server, I am setting the currently playing song as the Activity.
        node = await lavalink.get_guild_node(event.guild_id)

        await plugin.bot.update_presence(
            activity = hikari.Activity(
                name = f"{node.now_playing.track.info.author} - {node.now_playing.track.info.title}",
                type = hikari.ActivityType.PLAYING
            )
        )

    async def track_finish(self, lavalink: lavasnek_rs.Lavalink, event: lavasnek_rs.TrackFinish) -> None:
        logging.info("Track finished on guild: %s", event.guild_id)

        node = await lavalink.get_guild_node(event.guild_id)

        if not node.queue:
            await plugin.bot.update_presence(
                activity = hikari.Activity(
                    name = f"/play",
                    type = hikari.ActivityType.LISTENING
                )
            )

    async def track_exception(self, lavalink: lavasnek_rs.Lavalink, event: lavasnek_rs.TrackException) -> None:
        logging.warning("Track exception event happened on guild: %d", event.guild_id)
        
        # If a track was unable to be played, skip it
        skip = await lavalink.skip(event.guild_id)
        node = await lavalink.get_guild_node(event.guild_id)

        if not node:
            return

        if skip and not node.queue and not node.now_playing:
            await lavalink.stop(event.guild_id)

class NowPlayingButtons(neon.ComponentMenu):
    @neon.button("Play/Pause", "play_pause", hikari.ButtonStyle.PRIMARY, emoji = "⏯")
    async def play_pause(self, button : neon.Button) -> None:
        node = await plugin.bot.d.lavalink.get_guild_node(self.context.guild_id)
        if not node.is_paused:
            await plugin.bot.d.lavalink.pause(self.context.guild_id)
            await self.inter.create_initial_response(
                hikari.ResponseType.MESSAGE_CREATE,
                content = f":pause_button: Paused player",
                flags = hikari.MessageFlag.EPHEMERAL
            )
        else:
            await plugin.bot.d.lavalink.resume(self.context.guild_id)
            await self.inter.create_initial_response(
                hikari.ResponseType.MESSAGE_CREATE,
                content = f":arrow_forward: Resumed player",
                flags = hikari.MessageFlag.EPHEMERAL
            )
    
    @neon.button("Skip", "skip", hikari.ButtonStyle.PRIMARY, emoji = '⏩')
    async def skip(self, button : neon.Button) -> None:
        skip = await plugin.bot.d.lavalink.skip(self.context.guild_id)
        node = await plugin.bot.d.lavalink.get_guild_node(self.context.guild_id)

        if not skip:
            await self.inter.create_initial_response(
                hikari.ResponseType.MESSAGE_CREATE,
                content = f":caution: Nothing to skip",
                flags = hikari.MessageFlag.EPHEMERAL
            )
        else:
            # If the queue is empty, the next track won't start playing (because there isn't any),
            # so we stop the player.
            if not node.queue and not node.now_playing:
                await plugin.bot.d.lavalink.stop(self.context.guild_id)
                await self.edit_msg(
                    embed = hikari.Embed(
                        description = "Nothing is playing."
                    )
                )
            
            await self.inter.create_initial_response(
                hikari.ResponseType.MESSAGE_CREATE,
                content = f":fast_forward: Skipped: {skip.track.info.title}",
                flags = hikari.MessageFlag.EPHEMERAL
            )
        
    @neon.button("Stop", "stop", hikari.ButtonStyle.DANGER, emoji = '⏹')
    async def stop(self, button : neon.Button) -> None:
        await plugin.bot.d.lavalink.stop(self.context.guild_id)
        await self.edit_msg(
            embed = hikari.Embed(
                description = "Nothing is playing."
            )
        )
        await self.inter.create_initial_response(
            hikari.ResponseType.MESSAGE_CREATE,
            content = f":stop_button: Stopped playing",
            flags = hikari.MessageFlag.EPHEMERAL
        )

plugin = lightbulb.Plugin("Music")

async def _join(ctx: lightbulb.Context) -> Optional[hikari.Snowflake]:
    assert ctx.guild_id is not None

    states = plugin.bot.cache.get_voice_states_view_for_guild(ctx.guild_id)
    voice_state = [state async for state in states.iterator().filter(lambda i: i.user_id == ctx.author.id)]
    bot_voice_state = [state async for state in states.iterator().filter(lambda i: i.user_id == ctx.bot.get_me().id)]

    if not voice_state:
        await ctx.respond("Connect to a voice channel first.")
        return None

    channel_id = voice_state[0].channel_id

    if bot_voice_state:
        if channel_id != bot_voice_state[0].channel_id:
            await ctx.respond("I am already playing in another Voice Channel.")
            return None

    if HIKARI_VOICE:
        assert ctx.guild_id is not None

        await plugin.bot.update_voice_state(ctx.guild_id, channel_id, self_deaf=True)
        connection_info = await plugin.bot.d.lavalink.wait_for_full_connection_info_insert(ctx.guild_id)

    else:
        try:
            connection_info = await plugin.bot.d.lavalink.join(ctx.guild_id, channel_id)
        except TimeoutError:
            await ctx.respond(
                "I was unable to connect to the voice channel, maybe missing permissions? or some internal issue."
            )
            return None

    await plugin.bot.d.lavalink.create_session(connection_info)

    return channel_id

async def requester_check(ctx: lightbulb.Context) -> bool:
    states = plugin.bot.cache.get_voice_states_view_for_guild(ctx.guild_id)
    voice_state = [state async for state in states.iterator().filter(lambda i: i.user_id == ctx.author.id)]
    bot_voice_state = [state async for state in states.iterator().filter(lambda i: i.user_id == ctx.bot.get_me().id)]

    if not voice_state:
        return False

    channel_id = voice_state[0].channel_id

    if bot_voice_state:
        if channel_id != bot_voice_state[0].channel_id:
            return False
        else:
            return True
    else:
        return False

@plugin.listener(hikari.ShardReadyEvent)
async def start_lavalink(event: hikari.ShardReadyEvent) -> None:
    """Event that triggers when the hikari gateway is ready."""

    builder = (
        # TOKEN can be an empty string if you don't want to use lavasnek's discord gateway.
        lavasnek_rs.LavalinkBuilder(event.my_user.id, TOKEN)
        # This is the default value, so this is redundant, but it's here to show how to set a custom one.
        .set_host("127.0.0.1").set_password(LAVALINK_PASSWORD)
    )

    if HIKARI_VOICE:
        builder.set_start_gateway(False)

    lava_client = await builder.build(EventHandler())

    plugin.bot.d.lavalink = lava_client

    plugin.bot.unsubscribe(hikari.ShardReadyEvent, start_lavalink)


@plugin.command()
@lightbulb.add_checks(lightbulb.guild_only)
@lightbulb.command("join", "Joins the voice channel you are in.")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def join(ctx: lightbulb.Context) -> None:
    """Joins the voice channel you are in."""
    channel_id = await _join(ctx)

    if channel_id:
        await ctx.respond(f"Joined <#{channel_id}>")


@plugin.command()
@lightbulb.add_checks(lightbulb.guild_only, lightbulb.Check(requester_check, requester_check))
@lightbulb.command("leave", "Leaves the voice channel the bot is in, clearing the queue.")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def leave(ctx: lightbulb.Context) -> None:
    """Leaves the voice channel the bot is in, clearing the queue."""

    await plugin.bot.d.lavalink.destroy(ctx.guild_id)

    if HIKARI_VOICE:
        if ctx.guild_id is not None:
            await plugin.bot.update_voice_state(ctx.guild_id, None)
            await plugin.bot.d.lavalink.wait_for_connection_info_remove(ctx.guild_id)
    else:
        await plugin.bot.d.lavalink.leave(ctx.guild_id)

    # Destroy nor leave remove the node nor the queue loop, you should do this manually.
    await plugin.bot.d.lavalink.remove_guild_node(ctx.guild_id)
    await plugin.bot.d.lavalink.remove_guild_from_loops(ctx.guild_id)

    await ctx.respond("Left voice channel")


@plugin.command()
@lightbulb.add_checks(lightbulb.guild_only)
@lightbulb.option("query", "The query to search for.", modifier=lightbulb.OptionModifier.CONSUME_REST)
@lightbulb.command("play", "Searches the query on youtube, or adds the URL to the queue.", auto_defer = True)
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def play(ctx: lightbulb.Context) -> None:
    """Searches the query on youtube, or adds the URL to the queue."""

    query = ctx.options.query

    if not query:
        await ctx.respond("Please specify a query.")
        return None

    con = plugin.bot.d.lavalink.get_guild_gateway_connection_info(ctx.guild_id)
    # Join the user's voice channel if the bot is not in one.
    #if not con:
    await _join(ctx)

    playlist = False
    isAlbum = False
    isSpotifySong = False
    i = 0

    if "https://open.spotify.com/" in query:
        sp = spotipy.Spotify(auth_manager = SpotifyClientCredentials(client_id = SPOTIFY_CLIENT_ID,client_secret = SPOTIFY_CLIENT_SECRET))
        if "playlist" in query:
            playlist = True
            playlist_link = query
            playlist_URI = playlist_link.split("/")[-1].split("?")[0]
            track_uris = [x["track"]["uri"] for x in sp.playlist_tracks(playlist_URI)["items"]]
            playlist_info = sp.playlist(playlist_URI, fields = "name")
            await ctx.respond(
                embed = hikari.Embed(
                    description = f"[{playlist_info['name']}]({query}) ({len(track_uris)} tracks) added to queue [{ctx.author.mention}].",
                    colour = 0x76ffa1
                )  
            )
            for track in sp.playlist_tracks(playlist_URI)["items"]:
                track_name = track["track"]["name"]
                track_artist = track["track"]["artists"][0]["name"]
                queryfinal = f"{track_name} " + " " + f"{track_artist}" 
                result = f"ytmsearch:{queryfinal}"
                query_information = await plugin.bot.d.lavalink.get_tracks(result)
                if not query_information.tracks:
                    continue
                await plugin.bot.d.lavalink.play(ctx.guild_id, query_information.tracks[0]).requester(ctx.author.id).queue()
                i += 1
    
        elif "album" in query:
            isAlbum = True
            album_link = f"{query}"
            album_id= album_link.split("/")[-1].split("?")[0]
            for track in sp.album_tracks(album_id)["items"]:
                track_name = track["name"]
                track_artist = track["artists"][0]["name"]
                queryfinal = f"{track_name} " + f"{track_artist}" 
                result = f"ytmsearch:{queryfinal}"
                query_information = await plugin.bot.d.lavalink.get_tracks(result)
                if not query_information.tracks:
                    continue
                await plugin.bot.d.lavalink.play(ctx.guild_id, query_information.tracks[0]).requester(ctx.author.id).queue()
                i += 1
        
        elif "track" in query:
            isSpotifySong = True
            track_link = query
            track_id = track_link.split("/")[-1].split("?")[0]
            track_info = sp.track(track_id)
            track_name = track_info["name"]
            track_artist = track_info["artists"][0]["name"]
            queryfinal = f"{track_artist} {track_name}"
            result = f"ytmsearch:{queryfinal}"
            query_information = await plugin.bot.d.lavalink.get_tracks(result)
            await plugin.bot.d.lavalink.play(ctx.guild_id, query_information.tracks[0]).requester(ctx.author.id).queue()

        if isAlbum:
            album_info = sp.album(album_id)
            await ctx.respond(
                embed = hikari.Embed(
                    description = f"[{album_info['name']}]({query}) ({i} tracks) has been added to queue [{ctx.author.mention}].",
                    colour = 0x76ffa1
                )  
            )
        elif isSpotifySong:
            await ctx.respond(
                embed = hikari.Embed(
                    description = f"[{track_name}]({query}) added to queue [{ctx.author.mention}]",
                    colour = 0x76ffa1
                )  
            )

    # Search the query, auto_search will get the track from a url if possible, otherwise,
    # it will search the query on youtube.
    else:
        query_information = await plugin.bot.d.lavalink.auto_search_tracks(query)

        if query_information.playlist_info.name:
            playlist = True

        if not query_information.tracks:  # tracks is empty
            await ctx.respond("Could not find any video of the search query.")
            return

        if playlist:
            try:
                for track in query_information.tracks:
                    await plugin.bot.d.lavalink.play(ctx.guild_id, track).requester(ctx.author.id).queue()
            except lavasnek_rs.NoSessionPresent:
                await ctx.respond(f"Use `{PREFIX}join` first")
        
            await ctx.respond(
                embed = hikari.Embed(
                    description = f"{query_information.playlist_info.name} ({len(query_information.tracks)} tracks) added to queue [{ctx.author.mention}]",
                    colour = 0x76ffa1
                )
        )
        else:
            try:
                # `.requester()` To set who requested the track, so you can show it on now-playing or queue.
                # `.queue()` To add the track to the queue rather than starting to play the track now.
                await plugin.bot.d.lavalink.play(ctx.guild_id, query_information.tracks[0]).requester(ctx.author.id).queue()
            except lavasnek_rs.NoSessionPresent:
                await ctx.respond(f"Use `{PREFIX}join` first")
                return

            await ctx.respond(
                embed = hikari.Embed(
                    description = f"[{query_information.tracks[0].info.title}]({query_information.tracks[0].info.uri}) added to queue [{ctx.author.mention}]",
                    colour = 0x76ffa1
                )
            )
    
    


@plugin.command()
@lightbulb.add_checks(lightbulb.guild_only, lightbulb.Check(requester_check, requester_check))
@lightbulb.command("stop", "Stops the current song and clears queue.")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def stop(ctx: lightbulb.Context) -> None:
    """Stops the current song (skip to continue)."""

    await plugin.bot.d.lavalink.stop(ctx.guild_id)
    node = await plugin.bot.d.lavalink.get_guild_node(ctx.guild_id)
    node.queue = []
    await plugin.bot.d.lavalink.set_guild_node(ctx.guild_id, node)
    skip = await plugin.bot.d.lavalink.skip(ctx.guild_id)
    
    await ctx.respond(
        embed = hikari.Embed(
            description = ":stop_button: Stopped playing",
            colour = 0xd25557
        )
    )


@plugin.command()
@lightbulb.add_checks(lightbulb.guild_only, lightbulb.Check(requester_check, requester_check))
@lightbulb.command("skip", "Skips the current song.")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def skip(ctx: lightbulb.Context) -> None:
    """Skips the current song."""

    skip = await plugin.bot.d.lavalink.skip(ctx.guild_id)
    node = await plugin.bot.d.lavalink.get_guild_node(ctx.guild_id)

    if not skip:
        await ctx.respond(":caution: Nothing to skip")
    else:
        # If the queue is empty, the next track won't start playing (because there isn't any),
        # so we stop the player.
        if not node.queue and not node.now_playing:
            await plugin.bot.d.lavalink.stop(ctx.guild_id)

        await ctx.respond(
            
            embed = hikari.Embed(
                description =   f":fast_forward: Skipped: [{skip.track.info.title}]({skip.track.info.uri})",
                colour = 0xd25557
            )
        )


@plugin.command()
@lightbulb.add_checks(lightbulb.guild_only, lightbulb.Check(requester_check, requester_check))
@lightbulb.command("pause", "Pauses the current song.")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def pause(ctx: lightbulb.Context) -> None:
    """Pauses the current song."""

    await plugin.bot.d.lavalink.pause(ctx.guild_id)
    await ctx.respond(
        embed = hikari.Embed(
            description = ":pause_button: Paused player",
            colour = 0xf9c62b
        )
    )


@plugin.command()
@lightbulb.add_checks(lightbulb.guild_only, lightbulb.Check(requester_check, requester_check))
@lightbulb.command("resume", "Resumes playing the current song.")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def resume(ctx: lightbulb.Context) -> None:
    """Resumes playing the current song."""

    await plugin.bot.d.lavalink.resume(ctx.guild_id)
    await ctx.respond(
        embed = hikari.Embed(
            description = ":arrow_forward: Resumed player",
            colour = 0x76ffa1
        )
    )

@plugin.command()
@lightbulb.add_checks(lightbulb.guild_only)
@lightbulb.command("nowplaying", "Gets the song that's currently playing.", aliases=["np"])
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def now_playing(ctx: lightbulb.Context) -> None:
    """Gets the song that's currently playing."""

    node = await plugin.bot.d.lavalink.get_guild_node(ctx.guild_id)

    if not node or not node.now_playing:
        await ctx.respond("Nothing is playing at the moment.")
        return

    # for queue, iterate over `node.queue`, where index 0 is now_playing.
    queue_amount = 0
    for q in node.queue:
        queue_amount += int(q.track.info.length)

    length = divmod(node.now_playing.track.info.length, 60000)
    position = divmod(node.now_playing.track.info.position, 60000)
    queue_amount = divmod(queue_amount, 60000)

    menu = NowPlayingButtons(ctx)
    resp = await ctx.respond(
        embed = hikari.Embed(
            title = "Now Playing",
            description = f"[{node.now_playing.track.info.title}]({node.now_playing.track.info.uri})",
            colour = 0x76ffa1
        ).add_field(
            name = "Artist:", value = f"{node.now_playing.track.info.author}", inline = True
        ).add_field(
            name = "Position:", value = f"{int(position[0])}:{round(position[1]/1000):02}/{int(length[0])}:{round(length[1]/1000):02}", inline = True
        ).add_field(
            name = "Requested by:", value = f"<@!{node.now_playing.requester}>", inline = True
        ).add_field(
            name = "Up Next:", value = f"[{node.queue[1].track.info.title}]({node.queue[1].track.info.uri})" if len(node.queue) > 1 else f"Nothing else in queue"
        ).set_footer(
            text = f"Total Queue Length : {int(queue_amount[0])}:{round(queue_amount[1]/1000):02}"
        ).set_thumbnail(
            f"https://img.youtube.com/vi/{node.now_playing.track.info.identifier}/maxresdefault.jpg"
        ),
        #components = menu.build()
    )
    #await menu.run(resp)

@plugin.command()
@lightbulb.add_checks(lightbulb.guild_only)
@lightbulb.command("queue", "Shows the next 10 songs in the queue", aliases = ['q'])
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def queue(ctx : lightbulb.Context) -> None:
    node = await plugin.bot.d.lavalink.get_guild_node(ctx.guild_id)

    if not node or not node.queue:
        await ctx.respond("Nothing is playing at the moment.")
        return
    
    if len(node.queue) == 1:
        await ctx.respond("Nothing in queue")
        return
    else:
        length = divmod(node.now_playing.track.info.length, 60000)
        queueDescription = f"Now playing: [{node.now_playing.track.info.title}]({node.now_playing.track.info.uri}) `{int(length[0])}:{round(length[1]/1000):02}` [<@!{node.now_playing.requester}>] \n\nUp next:"
        # EmbPag.add_line(f"Now playing: [{node.now_playing.track.info.title}]({node.now_playing.track.info.uri}) `{l_minutes}:{l_seconds if first_n != 0 else f'0{l_seconds}'}` [<@!{node.now_playing.requester}>] \n\nUp next:")
        i = 1
        while True:
            length = divmod(node.queue[i].track.info.length, 60000)
            queueDescription = queueDescription + f"\n[{i}. {node.queue[i].track.info.title}]({node.queue[i].track.info.uri}) `{int(length[0])}:{round(length[1]/1000):02}` [<@!{node.queue[i].requester}>]"
            i += 1
            if i >= len(node.queue) or i > 10:
                break
    
        queueEmbed = hikari.Embed(
            title = "Queue",
            description = queueDescription,
            colour = 0x76ffa1
        )

        await ctx.respond(embed = queueEmbed)
    #navigator = nav.ButtonNavigator(EmbPag.build_pages())
    #await navigator.run(ctx)

@plugin.command()
@lightbulb.add_checks(lightbulb.guild_only, lightbulb.Check(requester_check, requester_check))
@lightbulb.option("time", "What time you would like to seek to.", modifier=lightbulb.OptionModifier.CONSUME_REST)
@lightbulb.command("seek", "Seek to a specific point in a song.")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def seek(ctx: lightbulb.Context) -> None:
    states = plugin.bot.cache.get_voice_states_view_for_guild(ctx.guild_id)
    voice_state = [state async for state in states.iterator().filter(lambda i: i.user_id == ctx.author.id)]
    if not voice_state:
        embed = hikari.Embed(title="You are not in a voice channel.", colour=0xC80000)
        await ctx.respond(embed=embed)
        return None
    node = await plugin.bot.d.lavalink.get_guild_node(ctx.guild_id)
    if not node or not node.now_playing:
        embed = hikari.Embed(title="There are no songs playing at the moment.", colour=0xC80000)
        await ctx.respond(embed=embed)
        return
    if not (match := re.match(TIME_REGEX, ctx.options.time)):
            embed = hikari.Embed(title="Invalid time entered.", colour=0xC80000)
            await ctx.respond(embed=embed)
    if match.group(3):
            secs = (int(match.group(1)) * 60) + (int(match.group(3)))
    else:
            secs = int(match.group(1))
    await plugin.bot.d.lavalink.seek_millis(ctx.guild_id, secs * 1000)
    embed = hikari.Embed(title=f"Seeked {node.now_playing.track.info.title}.", colour=0xD7CBCC)
    try:
        embed.set_thumbnail(f"https://img.youtube.com/vi/{node.now_playing.track.info.identifier}/maxresdefault.jpg")
    except:
        pass
    try:
        length = divmod(node.now_playing.track.info.length, 60000)

        embed.add_field(name="Current Position", value=f"{ctx.options.time}/{int(length[0])}:{round(length[1]/1000):02}")
    except:
        pass
    await ctx.respond(embed=embed)

@plugin.command()
@lightbulb.add_checks(lightbulb.guild_only)
@lightbulb.option("song", "The name of the song you want lyrics for.", modifier=lightbulb.OptionModifier.CONSUME_REST, required = False)
@lightbulb.command("lyrics", "Searches for the lyrics of the current song or any song of your choice!")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def lyrics(ctx: lightbulb.Context) -> None:
    genius = lyricsgenius.Genius(GENIUS_ACCESS_TOKEN)
    genius.verbose = True
    genius.remove_section_headers = False
    genius.skip_non_songs = True

    node = await plugin.bot.d.lavalink.get_guild_node(ctx.guild_id)

    if not node or not node.now_playing or ctx.options.song:
        song = genius.search_song(f"{ctx.options.song}")
        title = song.full_title
    else:
        song = genius.search_song(f"{node.now_playing.track.info.title}", f"{node.now_playing.track.info.author}")
        title = node.now_playing.track.info.title

    if not song:
        await ctx.respond(
            embed = hikari.Embed(
                title="Lyrics Search Failed", 
                description=f"Could not find the song. Check the song and artist name and try again.", 
                color=0xC80000
            )
        )
        return

    test_stirng = f"{song.lyrics}"
    total = 1
    for i in range(len(test_stirng)):
        if(test_stirng[i] == ' ' or test_stirng == '\n' or test_stirng == '\t'):
            total = total + 1
    if total > 650:
        embed=hikari.Embed(title="Character Limit Exceeded!", description=f"The lyrics in this song are too long. (Over 6000 characters)", color=0xC80000)
        await ctx.respond(embed=embed)
        return
    embed2=hikari.Embed(title=f"{title}" ,description=f"{song.lyrics}", color=0xD7CBCC)
    await ctx.respond(embed=embed2)

if HIKARI_VOICE:

    @plugin.listener(hikari.VoiceStateUpdateEvent)
    async def voice_state_update(event: hikari.VoiceStateUpdateEvent) -> None:
        plugin.bot.d.lavalink.raw_handle_event_voice_state_update(
            event.state.guild_id,
            event.state.user_id,
            event.state.session_id,
            event.state.channel_id,
        )

    @plugin.listener(hikari.VoiceServerUpdateEvent)
    async def voice_server_update(event: hikari.VoiceServerUpdateEvent) -> None:
        await plugin.bot.d.lavalink.raw_handle_event_voice_server_update(event.guild_id, event.endpoint, event.token)


def load(bot: lightbulb.BotApp) -> None:
    bot.add_plugin(plugin)


def unload(bot: lightbulb.BotApp) -> None:
    bot.remove_plugin(plugin)