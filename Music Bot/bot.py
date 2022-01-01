import os

import hikari
import lightbulb
from consts import OWNER_ID, PREFIX, TOKEN

# You may want to enable ALL intents here
bot = lightbulb.BotApp(token=TOKEN, prefix=PREFIX, owner_ids=[OWNER_ID], case_insensitive_prefix_commands=True, delete_unbound_commands=True)


@bot.listen()
async def starting_load_extensions(_: hikari.StartingEvent) -> None:
    """Load the music extension when Bot starts."""
    bot.load_extensions("music_plugin")


@bot.command()
@lightbulb.command("ping", "The bot's ping.")
@lightbulb.implements(lightbulb.PrefixCommand, lightbulb.SlashCommand)
async def ping(ctx: lightbulb.Context) -> None:
    """Typical Ping-Pong command"""
    await ctx.respond("Ping?")

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