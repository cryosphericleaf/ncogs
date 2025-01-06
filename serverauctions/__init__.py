from .auction import ServerAuctions

__red_end_user_data_statement__ = "This cog does not store any user data except for user ids to track auctions"

async def setup(bot):
    await bot.add_cog(ServerAuctions(bot))
