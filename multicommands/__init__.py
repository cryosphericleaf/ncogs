from .commands import MultiCommands

__red_end_user_data_statement__ = "This cog does not store any user data"

async def setup(bot):
    await bot.add_cog(MultiCommands(bot))
