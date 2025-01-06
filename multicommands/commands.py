# https://github.com/tmercswims/tmerc-cogs/blob/v3/nestedcommands/nestedcommands.py

from redbot.core import commands

class MultiCommands(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def red_delete_data_for_user(self, **kwargs):
        """Nothing to delete"""
        return

    async def _usable(self, ctx: commands.Context, command_text: str) -> bool:
        prefix = tuple(await self.bot.get_prefix(ctx.message))
        if not command_text.startswith(prefix):
            return False
        if command_text[1:].startswith(("pipe", "invoke")):
            print(command_text[1:])
            await ctx.send("cant use `pipe` or `invoke` inside `pipe` or `invoke`")
            return False
        return True

    @commands.command()
    async def invoke(self, ctx: commands.Context, delay: int = 0, *,commands_text: str):
        """
        Simply runs multiple commands in order separated by a newline.


        Usage:
        ```[p]invoke
        [p]command1
        [p]command2
        [p]command3```
        """
        message = ctx.message
        commands = commands_text.split("\n")

        for command_text in commands:
            command_text = command_text.strip()
            if not await self._usable(ctx, command_text):
                continue

            message.content = command_text
            await ctx.send(f"-# invoking `{message.content}`")
            await self.bot.process_commands(message)

    @commands.command()
    async def pipe(self, ctx: commands.Context, *,commands_text: str):
        """
        Runs multiple commands in order separated by a newline.
        Each command (except the first) uses the bot's previous message as an argument for the next.

        Usage:
        ```[p]pipe
        [p]command1
        [p]command2
        [p]command3```
        """

        message = ctx.message
        commands = commands_text.split("\n")
        invoked_command = False
        last_message = ""
      
        for command_text in commands:
            command_text = command_text.strip()
            if not await self._usable(ctx, command_text):
                continue
            if invoked_command == True:
                last_message = (await anext(message.channel.history(limit=1))).content

            if last_message:
                message.content = command_text + " " + last_message
            else:
                message.content = command_text 
        
            await ctx.send(f"-# invoking `{message.content}`")
            await self.bot.process_commands(message)
            invoked_command = True
            last_message = ""

    