import os

import hikari
import lightbulb
from consts import OWNER_ID, PREFIX, TOKEN
from time import time
from random import randint
from datetime import datetime

# You may want to enable ALL intents here
bot = lightbulb.BotApp(token=TOKEN, prefix=lightbulb.when_mentioned_or(PREFIX), owner_ids=[OWNER_ID], case_insensitive_prefix_commands=True, delete_unbound_commands=True, allow_color=False, default_enabled_guilds = [744567167927975986, 740589508365385839])


@bot.listen()
async def starting_load_extensions(_: hikari.StartingEvent) -> None:
    """Load the music extension when Bot starts."""
    bot.load_extensions("music_plugin")


@bot.command()
@lightbulb.command("ping", "The bot's ping.")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def ping(ctx: lightbulb.Context) -> None:
    """Typical Ping-Pong command"""
    start = time()
    msg = await ctx.respond(
		embed = hikari.Embed(
			title = "Ping",
			description = "Pong!",
			color = randint(0, 0xffffff)
		), 
		reply = True
	)
    end = time()

    await msg.edit(embed = hikari.Embed(
			title = "Ping",
			description = f"**Heartbeat**: {ctx.app.heartbeat_latency * 1000:,.0f} ms \n**Latency** : {(end - start) * 1000:,.0f} ms",
			color = randint(0, 0xffffff),
            timestamp = datetime.now().astimezone()
		)
	)

@bot.command()
@lightbulb.command("about", "About the bot.")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def about(ctx : lightbulb.Context) -> None:
    await ctx.respond(f"Adding this soon.")

if __name__ == "__main__":
    if os.name != "nt":
        import uvloop

        uvloop.install()

    bot.run()