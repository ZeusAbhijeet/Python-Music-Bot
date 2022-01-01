import logging
from typing import Optional

import hikari
import lightbulb
import lavasnek_rs
import random
from consts import LAVALINK_PASSWORD, PREFIX, TOKEN
from lightbulb.utils import pag, nav
from lightbulb.ext import neon

# If True connect to voice with the hikari gateway instead of lavasnek_rs's
HIKARI_VOICE = False

EmbPag = pag.EmbedPaginator(max_lines = 10)

class EventHandler:
    """Events from the Lavalink server"""

    async def track_start(self, _: lavasnek_rs.Lavalink, event: lavasnek_rs.TrackStart) -> None:
        logging.info("Track started on guild: %s", event.guild_id)

    async def track_finish(self, _: lavasnek_rs.Lavalink, event: lavasnek_rs.TrackFinish) -> None:
        logging.info("Track finished on guild: %s", event.guild_id)

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

@EmbPag.embed_factory()
def build_embed(page_index, page_content) -> hikari.Embed:
    return hikari.Embed(
        title = "Queue",
        description = page_content,
        colour = 0x76ffa1
    ).set_footer(text = f"Page {page_index}")

async def _join(ctx: lightbulb.Context) -> Optional[hikari.Snowflake]:
    assert ctx.guild_id is not None

    states = plugin.bot.cache.get_voice_states_view_for_guild(ctx.guild_id)
    voice_state = [state async for state in states.iterator().filter(lambda i: i.user_id == ctx.author.id)]

    if not voice_state:
        await ctx.respond("Connect to a voice channel first.")
        return None

    channel_id = voice_state[0].channel_id

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
@lightbulb.add_checks(lightbulb.guild_only)
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
@lightbulb.command("play", "Searches the query on youtube, or adds the URL to the queue.")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def play(ctx: lightbulb.Context) -> None:
    """Searches the query on youtube, or adds the URL to the queue."""

    query = ctx.options.query

    if not query:
        await ctx.respond("Please specify a query.")
        return None

    con = plugin.bot.d.lavalink.get_guild_gateway_connection_info(ctx.guild_id)
    # Join the user's voice channel if the bot is not in one.
    if not con:
        await _join(ctx)

    # Search the query, auto_search will get the track from a url if possible, otherwise,
    # it will search the query on youtube.
    query_information = await plugin.bot.d.lavalink.auto_search_tracks(query)

    playlist = False

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
@lightbulb.add_checks(lightbulb.guild_only)
@lightbulb.command("stop", "Stops the current song (skip to continue).")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def stop(ctx: lightbulb.Context) -> None:
    """Stops the current song (skip to continue)."""

    await plugin.bot.d.lavalink.stop(ctx.guild_id)
    node = await plugin.bot.d.lavalink.get_guild_node(ctx.guild_id)
    node.queue = []
    await plugin.bot.d.lavalink.set_guild_node(ctx.guild_id, node)
    await ctx.respond(
        embed = hikari.Embed(
            description = ":stop_button: Stopped playing",
            colour = 0xd25557
        )
    )


@plugin.command()
@lightbulb.add_checks(lightbulb.guild_only)
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
@lightbulb.add_checks(lightbulb.guild_only)
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
@lightbulb.add_checks(lightbulb.guild_only)
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
@lightbulb.command("shuffle", "Shuffles the queue.")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def shuffle(ctx : lightbulb.Context) -> None:

    node = await plugin.bot.d.lavalink.get_guild_node(ctx.guild_id)

    if not node or not node.queue:
        await ctx.respond("Nothing is playing at the moment.")
        return

    old_queue : list = node.queue
    if old_queue and len(old_queue) > 1:
        first_q = old_queue[0]
        old_queue.pop(0)
        old_queue = random.sample(old_queue, len(old_queue))
        old_queue.insert(0, first_q)

        node.queue = old_queue
        
        await plugin.bot.d.lavalink.set_guild_node(ctx.guild_id, node)
    
    await ctx.respond("Shuffled.")


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
    amount = node.now_playing.track.info.length
    millis = int(amount)
    l_seconds=(millis/1000)%60
    l_seconds = int(l_seconds)
    l_minutes=(millis/(1000*60))%60
    l_minutes = int(l_minutes)
    first_n = int(l_seconds/10)
    queue_amount = 0
    for q in node.queue:
        queue_amount += int(q.track.info.length)
    q_seconds=(queue_amount/1000)%60
    q_seconds = int(q_seconds)
    q_minutes=(queue_amount/(1000*60))%60
    q_minutes = int(q_minutes)
    first_n_q = int(q_seconds/10)

    menu = NowPlayingButtons(ctx)
    resp = await ctx.respond(
        embed = hikari.Embed(
            title = "Now Playing",
            description = f"[{node.now_playing.track.info.title}]({node.now_playing.track.info.uri})",
            colour = 0x76ffa1
        ).add_field(
            name = "Length:", value = f"{l_minutes}:{l_seconds if first_n != 0 else f'0{l_seconds}'}", inline = True
        ).add_field(
            name = "Requested by:", value = f"<@!{node.now_playing.requester}>", inline = True
        ).add_field(
            name = "Up Next:", value = f"[{node.queue[1].track.info.title}]({node.queue[1].track.info.uri})" if len(node.queue) > 1 else f"Nothing else in queue"
        ).set_footer(
            text = f"Total Queue Length : {q_minutes}:{q_seconds if first_n_q != 0 else f'0{q_seconds}'}"
        ).set_thumbnail(
            f"https://img.youtube.com/vi/{node.now_playing.track.info.identifier}/maxresdefault.jpg"
        ),
        #components = menu.build()
    )
    #await menu.run(resp)

@plugin.command()
@lightbulb.add_checks(lightbulb.guild_only)
@lightbulb.command("queue", "Shows the song queue", aliases = ['q'])
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def queue(ctx : lightbulb.Context) -> None:
    node = await plugin.bot.d.lavalink.get_guild_node(ctx.guild_id)

    if not node or not node.queue:
        await ctx.respond("Nothing is playing at the moment.")
        return
    
    if len(node.queue) == 1:
        await ctx.respond("Nothing in queue")
    else:
        #page_queue = pag.StringPaginator(max_lines = 10, suffix = "```", prefix = "```")
        amount = node.now_playing.track.info.length
        millis = int(amount)
        l_seconds=(millis/1000)%60
        l_seconds = int(l_seconds)
        l_minutes=(millis/(1000*60))%60
        l_minutes = int(l_minutes)
        first_n = int(l_seconds/10)
        EmbPag.add_line(f"Now playing: [{node.now_playing.track.info.title}]({node.now_playing.track.info.uri}) `{l_minutes}:{l_seconds if first_n != 0 else f'0{l_seconds}'}` [<@!{node.now_playing.requester}>] \n\nUp next:")
        i = 1
        while True:
            amount = node.queue[i].track.info.length
            millis = int(amount)
            l_seconds=(millis/1000)%60
            l_seconds = int(l_seconds)
            l_minutes=(millis/(1000*60))%60
            l_minutes = int(l_minutes)
            first_n = int(l_seconds/10)
            EmbPag.add_line(f"[{i}. {node.queue[i].track.info.title}]({node.queue[i].track.info.uri}) `{l_minutes}:{l_seconds if first_n != 0 else f'0{l_seconds}'}` [<@!{node.queue[0].requester}>]")
            i += 1
            if i >= len(node.queue):
                break
        #print(f"{node.queue[1].start_time} {node.queue[0].end_time} {node.queue[1].track.info.position}")
    navigator = nav.ButtonNavigator(EmbPag.build_pages())
    await navigator.run(ctx)

@plugin.command()
@lightbulb.add_checks(lightbulb.guild_only)
@lightbulb.add_checks(lightbulb.owner_only)  # Optional
@lightbulb.option(
    "args", "The arguments to write to the node data.", required=False, modifier=lightbulb.OptionModifier.CONSUME_REST
)
@lightbulb.command("data", "Load or read data from the node.")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def data(ctx: lightbulb.Context) -> None:
    """Load or read data from the node.
    If just `data` is ran, it will show the current data, but if `data <key> <value>` is ran, it
    will insert that data to the node and display it."""

    node = await plugin.bot.d.lavalink.get_guild_node(ctx.guild_id)

    if not node:
        await ctx.respond("No node found.")
        return None

    if args := ctx.options.args:
        args = args.split(" ")

        if len(args) == 1:
            node.set_data({args[0]: args[0]})
        else:
            node.set_data({args[0]: args[1]})
    await ctx.respond(node.get_data())


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