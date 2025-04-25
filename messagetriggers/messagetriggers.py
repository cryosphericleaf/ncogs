

import random
import logging 
import asyncio
import discord
from types import CodeType
from typing import Tuple, List
from redbot.core import commands
from redbot.core.config import Config
from redbot.core.utils.menus import menu



class MessageTriggers(commands.Cog):
    def __init__(self, bot):
        self.bot: discord.Client = bot
        self.config = Config.get_conf(self, identifier=821912892189)
        self.config.register_global(triggers=[])
        self.logger = logging.getLogger('red.ncogs.auction')

        self.triggers: List[Tuple[str, CodeType, CodeType]] = []

    async def red_delete_data_for_user(self, **kwargs):
        """Nothing to delete"""
        return

    async def cog_load(self):
        await self.load_triggers()

    async def load_triggers(self):
        self.triggers.clear()
        all_triggers = await self.config.triggers()

        for name, condition, response in all_triggers:
            try:
                compiled_condition = compile(condition, "<condition>", "eval")
                compiled_response = compile(response, "<response>", "eval")
                self.triggers.append((name, compiled_condition, compiled_response))
            except Exception as e:
                self.logger.error(f"Error while compliling triggers: {str(e)}")

        self.logger.info("Loaded All Triggers") 


    @commands.is_owner()
    @commands.command()
    async def IF(self, ctx: commands.Context, *, command_str: str):
        """
        Create a new message trigger with a condition and a response.

        Usage:
            [p]IF <condition> SEND <response>

        Example:
            [p]IF "hello" in message.content SEND f"Hello, {message.author.name}!"

        <condition> and <response> are python expressions.
        The <condition> must evaluate to a boolean (`True` or `False`).
        The <response> must evaluate to a string.

        available variable: message, bot
        available module: random

        """
        if "SEND " not in command_str:
            await ctx.send(f"Syntax Error, Use: `[p]IF <condition> SEND <response>`")
            return
        try:
            condition = command_str.split("SEND ", 1)[0]
            response = command_str.split("SEND ", 1)[-1]

            message = ctx.message
            context = {"message": message, "bot": ctx.bot}
            _globals = {
                "__builtins__": {},
                "random": random,
            }
            m = eval(condition, _globals, context)
            if m not in (True, False):
                await ctx.send("The condition must evaluate to a bool.")
                return
            n = eval(response, _globals, context)
            if type(n) != str:
                await ctx.send("The content must evaluate to a string.")

            triggers = await self.config.triggers()

            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel

            try:
                await ctx.send("Give a name to your trigger.")
                new_name = (
                    await self.bot.wait_for("message", check=check, timeout=30.0)
                ).content.lower()

                for trigger_name, _, _ in triggers:
                    if new_name == trigger_name:
                        await ctx.send("This name's trigger already exists.")
                        return
            except asyncio.TimeoutError:
                await ctx.send("cancelled trigger creation.")
                return

            triggers.append((new_name, condition, response))
            await self.config.triggers.set(triggers)
            condition_code = compile(condition, "<string>", "eval")
            response_code = compile(response, "<string>", "eval")
            self.triggers.append((new_name, condition_code, response_code))

            await ctx.send("Trigger added!")
        except Exception as e:
            await ctx.send(f"Error In Parsing: {e}")

    @commands.group()
    async def trigger(self, ctx: commands.Context):
        """Base command for trigger actions."""
        pass

    @trigger.command(name="list")
    async def list_triggers(self, ctx: commands.Context):
        """List all trigger names (paginated)."""
        triggers = self.triggers

        if not triggers:
            return await ctx.send("No triggers are created.")

        pages = [
            "\n".join(name for name, _, _ in triggers[i : i + 10])
            for i in range(0, len(triggers), 10)
        ]

        await menu(ctx, pages)

    @trigger.command(name="get")
    async def gettrigger(self, ctx: commands.Context, name: str):
        """Get detailed info about a specific trigger."""
        triggers = await self.config.triggers()
        for trigger in triggers:
            if trigger[0].lower() == name.lower():
                condition, response = trigger[1], trigger[2]
                return await ctx.send(
                    f"`{trigger[0]}`\n"
                    f"```Condition: {condition}```"
                    f"```Response: {response}```"
                )
        await ctx.send(f"Trigger `{name}` not found.")

    @commands.is_owner()
    @trigger.command(name="remove")
    async def removetrigger(self, ctx: commands.Context, name: str):
        """Remove a trigger by name."""
        triggers = await self.config.triggers()
        new_triggers = [t for t in triggers if t[0].lower() != name.lower()]

        if len(new_triggers) == len(triggers):
            return await ctx.send(f"Trigger `{name}` not found.")

        await self.config.guild(ctx.guild).triggers.set(new_triggers)
        self.triggers = [t for t in self.triggers if t[0].lower() != name.lower()]
        await ctx.send(f"Trigger `{name}` has been removed.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if not self.triggers:
            return
        for _, condition, response in self.triggers:
            if eval(condition) == True:
                await message.channel.send(eval(response))
