

import re
import aiohttp
import discord 
from redbot.core import commands, Config
from redbot.core.utils.chat_formatting import pagify
from redbot.core.utils.views import SimpleMenu

from typing_extensions import Optional

class EmojiManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(self, identifier = 7543971538)
        self.config.register_guild(
            enabled = False,
            emoji_usage ={ }
        )

    async def red_delete_data_for_user(self, **kwargs):
        """Nothing to delete"""
        return

    @commands.group()
    @commands.bot_has_permissions(manage_emojis = True)
    @commands.has_permissions(manage_emojis = True)
    async def emoji(self, ctx: commands.Context):
        "Emoji management command group to add or remove emojis."
        pass

    @emoji.command()
    async def add(self, ctx: commands.Context, name: str, emoji: Optional[str] = None):
        "Add an emoji to the server."
        emoji_url = None
        if isinstance(emoji, str) :
            if not emoji.startswith("https://"):
                await ctx.send("invlaid link.")
                return
            emoji_url = emoji
        elif ctx.message.attachments:
            if not ctx.message.attachments[0].content_type.startswith("image"):
                await ctx.send("invalid attachment.")
                return
            emoji_url = ctx.message.attachments[0].url
        elif emoji == None:
            await ctx.send("Please provide an `image url` as the `second argument` or an `image/gif attachment.`")
            return
        # if emoji_url == None:
        #     await ctx.send("Please provide a `valid image attachement or image link or emoji`")
        try:
            image_data = await fetch_emoji(emoji_url)
            emoji = await ctx.guild.create_custom_emoji(name=name, image=image_data)
        except Exception as e:
            await ctx.send(f"error: `{str(e)}`")
            return 
        
        await ctx.send(f"added. {emoji}")

    @emoji.command()
    async def steal(self, ctx: commands.Context, emojis: commands.Greedy[discord.Emoji]):
        """Steal emojis to the server."""
        if not emojis:
            return await ctx.send("Please provide at least one emoji to steal.")

        added_emojis = []
        for emoji in emojis:
            try:
                image_data = await fetch_emoji(emoji.url)
                new_emoji = await ctx.guild.create_custom_emoji(name=emoji.name, image=image_data)
                added_emojis.append(new_emoji)
            except Exception as e:
                await ctx.send(f"failed to add {emoji}, err: `{str(e)}`")

        if added_emojis:
            await ctx.send(f"added {' '.join(str(e) for e in added_emojis)}")

    @emoji.command()
    async def remove(self, ctx: commands.Context, emojis: commands.Greedy[discord.Emoji]):
        """Remove emojis from the server."""
        if not emojis:
            return await ctx.send("Please provide at least one emoji to remove.")

        removed_emojis = []
        for emoji in emojis:
            try:
                await ctx.guild.delete_emoji(emoji)
                removed_emojis.append(emoji)
            except Exception as e:
                await ctx.send(f"failed to remove {emoji}, err: `{str(e)}`")

        if removed_emojis:
            await ctx.send(f"removed.")

    @commands.command()
    async def getemoji(self, ctx: commands.Context, emoji: discord.Emoji):
        "Get emoji url"
        await ctx.send(emoji.url)

    @commands.command()
    async def listemojis(self, ctx: commands.Context):
        "List the emojis of the server."
        emojis = ""
        for emoji in ctx.guild.emojis:
            emojis += f"{emoji} `<:{emoji.name}:{emoji.id}>`\n"
        if not emojis:
            await ctx.send("This server currently has no emojis.")
            return

        pages = pagify(emojis)
        await SimpleMenu(list(pages), disable_after_timeout=True).start(ctx)
    
    @commands.command()
    async def emojistats(self, ctx: commands.Context):
        "Display Emoji usage."
        emoji_usage = await self.config.guild(ctx.guild).emoji_usage()
        if not emoji_usage:
            await ctx.send("No emoji stats recorded yet.")
            return

        sorted_emojis = sorted(emoji_usage.items(), key=lambda x: x[1], reverse=True)
        stats_message = "\n".join(f"{emoji} {count}" for emoji, count in sorted_emojis)

        pages = pagify(stats_message)
        await SimpleMenu(list(pages), disable_after_timeout=True).start(ctx)

    @commands.command()
    @commands.has_permissions(manage_emojis = True)
    async def emojistatstoggle(self, ctx: commands.Context):
        "Enable or Disable emoji stats."
        enabled = await self.config.guild(ctx.guild).enabled()
        if enabled:
            await self.config.guild(ctx.guild).enabled.set(False)
            await ctx.send("disabled emojistats.")
        else:
            await self.config.guild(ctx.guild).enabled.set(True)
            await ctx.send("enabled emojistats.")

    @commands.command()
    @commands.has_permissions(manage_emojis = True)
    async def emojistatsreset(self, ctx: commands.Context):
        """Reset emoji stats."""
        await self.config.guild(ctx.guild).emoji_usage.set({})
        await ctx.send("Emoji stats have been reset.")

    @commands.command()
    @commands.has_permissions(manage_emojis = True)
    async def remove_non_existing_emojis_from_stats(self, ctx: commands.Context):
        emoji_usage: dict = await self.config.guild(ctx.guild).emoji_usage()
        existing_emojis = {f"<:{emoji.name}:{emoji.id}>" for emoji in ctx.guild.emojis}

        items = tuple(emoji_usage.items())

        for emoji_str, _ in items:
            if emoji_str not in existing_emojis:
                _ = emoji_usage.pop(emoji_str)

        await self.config.guild(ctx.guild).emoji_usage.set(emoji_usage)
        await ctx.send("done.")


        

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        enabled = await self.config.guild(message.guild).enabled()
        if not enabled:
            return

        emoji_usage = await self.config.guild(message.guild).emoji_usage()
        unique_emojis = set(re.findall(r"<a?:\w+:\d+>", message.content))

        for emoji_str in unique_emojis:  
            emoji_usage[emoji_str] = emoji_usage.get(emoji_str, 0) + 1

        await self.config.guild(message.guild).emoji_usage.set(emoji_usage)


async def fetch_emoji(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Failed, HTTP Status: {resp.status}")
            if int(resp.headers["Content-Length"]) > MAX_EMOJI_SIZE:
                raise Exception("Image larger than 256KB.")
        
            return await resp.read()
        
        
MAX_EMOJI_SIZE = 256 * 1024