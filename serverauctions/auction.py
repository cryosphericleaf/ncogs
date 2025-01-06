import discord
import asyncio
import logging
from redbot.core import commands, Config, bank
from datetime import datetime, timezone
from .view import AuctionSetup

class ServerAuctions(commands.Cog):
    """Auction management."""
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.log = logging.getLogger('red.ncogs.auction')
        self.config = Config.get_conf(self, identifier=666664321)
        self.config.register_guild(
            auctions=[],
            auction_count=0,
            use_bank=False
        )
        self.config.register_member(auctioneer=False)
        self.auction_tasks = {}
        self.auction_messages = {}
        self.bot.loop.create_task(self.initialize_pending_auctions())

        self.initializing_auctions = True

    async def red_delete_data_for_user(self, **kwargs):
        """Nothing to delete"""
        return

    def cog_unload(self) -> None:
        for task in self.auction_tasks.values():
            task.cancel()
        self.auction_tasks.clear()

    def get_cached_auction_message(self, auction_id: int) -> discord.Message:
        return self.auction_messages.get(auction_id)

    def cache_auction_message(self, auction_id: int, message: discord.Message):
        self.auction_messages[auction_id] = message

    async def initialize_pending_auctions(self):
        await self.bot.wait_until_ready()
        total_auctions = 0
        for guild in self.bot.guilds:
            guild_config = self.config.guild(guild)
            auctions = await guild_config.auctions()
            valid_auctions = []

            fetch_tasks = [self.try_fetch_message(guild, auction["thread_id"], auction["message_id"]) for auction in auctions]
            messages = await asyncio.gather(*fetch_tasks, return_exceptions=True)
            for auction, message in zip(auctions, messages):
                if isinstance(message, Exception) or not message:
                    continue
                if auction["auction_id"] not in self.auction_messages:
                    self.cache_auction_message(auction["auction_id"], message)

                task = asyncio.create_task(self.schedule_auction_end(message, auction))
                self.auction_tasks[auction["auction_id"]] = task
                valid_auctions.append(auction)
                total_auctions += 1

            await guild_config.auctions.set(valid_auctions)
        if total_auctions > 0:
            self.log.info(f"Scheduled {total_auctions} auctions across all guilds.")
        self.initializing_auctions = False

    async def schedule_auction_end(self, auction_message: discord.Message, auction_data: dict):
        now = datetime.now(timezone.utc).timestamp()
        remaining_time = auction_data["end_timestamp"] - now
        if remaining_time > 0:
            await asyncio.sleep(remaining_time)
        await self.close_auction(auction_message, auction_data["auction_id"])

    async def try_dm(self, user: discord.User, message: str) -> None:
        try:
            await user.send(message)
        except (discord.Forbidden, discord.HTTPException):
            pass

    async def try_fetch_message(self, guild, channel_id: int, message_id: int) -> discord.Message:
        try:
            channel = guild.get_channel(channel_id) or await guild.fetch_channel(channel_id)
            return await channel.fetch_message(message_id)
        except discord.NotFound:
           pass

    async def update_auction_data(self, guild_config: Config, auction_data: dict) -> None:
        async with guild_config.auctions() as auctions:
            for i, auction in enumerate(auctions):
                if auction["auction_id"] == auction_data["auction_id"]:
                    auctions[i] = auction_data
                    break

    async def get_auction_data(self, guild_config: Config, auction_id: int = None, thread_id: int = None) -> dict:
        async with guild_config.auctions() as auctions:
            for auction in auctions:
                if (auction_id and auction["auction_id"] == auction_id) or (thread_id and auction["thread_id"] == thread_id):
                    return auction
        return None

    async def clean_up_auction(self, guild_config: Config, auction_id: int) -> None:
        async with guild_config.auctions() as auctions:
            auctions[:] = [auction for auction in auctions if auction["auction_id"] != auction_id]
        if auction_id in self.auction_tasks:
            self.auction_tasks[auction_id].cancel()
            del self.auction_tasks[auction_id]
        self.auction_messages.pop(auction_id, None)

    async def close_auction(self, auction_message: discord.Message, auction_id: int, force_close = False) -> None:
        guild_config = self.config.guild(auction_message.guild)
        auction_data = await self.get_auction_data(guild_config, auction_id)
        use_bank = await guild_config.use_bank()

        embed = auction_message.embeds[0]
        embed.clear_fields()
        embed.title = f"~~{embed.title}~~ - Closed"
        embed.color = discord.Colour.red()
        guild = auction_message.guild
        host = guild.get_member(auction_data["host_id"]) or await guild.fetch_member(auction_data["host_id"])
        bidder = None

        if auction_data["current_bid"] is not None:
            bidder = guild.get_member(auction_data["current_bidder"]) or await guild.fetch_member(auction_data["current_bidder"])
            embed.add_field(name="Sold out to", value=f"{bidder.display_name}", inline=False)
            embed.add_field(name="Final Bid", value=f'{auction_data["current_bid"]}', inline=False)
            if use_bank:
                await bank.deposit_credits(host, auction_data["current_bid"])
        else:
            embed.add_field(name="Final bid", value="No bids were placed.", inline=False)

        if force_close:
            await auction_message.edit(content=f"# `#{auction_id}` was removed.", embed=None)
            await self.clean_up_auction(guild_config, auction_id)
            return
        else:
            await auction_message.edit(embed=embed)
            await auction_message.channel.edit(archived=True)
            await auction_message.channel.send(f"#{auction_data['auction_id']} has been closed.")

        await self.try_dm(host, f"-# Your auction [#{auction_data['auction_id']}]({auction_message.jump_url}) has been closed.")
        if bidder:
            await self.try_dm(bidder, f"-# Auction [#{auction_data['auction_id']}]({auction_message.jump_url}) solded out to you.")
        await self.clean_up_auction(guild_config, auction_id)


    def auction_initializing_check(ctx: commands.Context):
        if ctx.cog.initializing_auctions:
            return False
        return True

    @commands.group(aliases=["auc"], invoke_without_command=True)
    @commands.bot_has_permissions(manage_threads=True, manage_messages=True)
    async def auction(self, ctx: commands.Context) -> None:
        """Auction management command group."""
        pass

    async def can_create_auc(ctx: commands.Context) -> bool:
        return (
            await ctx.cog.config.member(ctx.author).auctioneer() or
            await ctx.bot.is_owner(ctx.author)
        )

    @auction.command()
    @commands.check(can_create_auc)
    async def create(self, ctx: commands.Context):
        """Create auction in current channel."""
        if not isinstance(ctx.channel, discord.TextChannel):
            await ctx.send("can only use this command in a Text Channel")
            return 
        auction_data = {
            "thread_id": None,
            "message_id": None,
            "host_id": ctx.author.id,
            "auction_id": None,
            "quick_sold": None,
            "current_bid": None,
            "current_bidder": None,
            "end_timestamp": None,
            "min_bid" : 1
        }
        await ctx.message.delete()
        embed = discord.Embed(title=f"#???", description="...", color=discord.Color.green())
        auc_setup_view = AuctionSetup(ctx, embed, auction_data, self)
        await ctx.send(embed=embed, view=auc_setup_view)
    
    @create.error
    async def create_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("you need to be an auctioneer to create auction.")

    @auction.command()
    @commands.check(auction_initializing_check)
    @commands.cooldown(1, 5, commands.BucketType.user)  
    async def bid(self, ctx: commands.Context, amount: int):
        """Place a bid on an auction.(used in the active auction thread)"""
        if len(str(amount)) > 1008:
            await ctx.send(f"too big..")
            return
        guild_config = self.config.guild(ctx.guild)
        use_bank = await guild_config.use_bank()  
        if use_bank:
            bal = await bank.get_balance(ctx.author)
            if bal < amount:
                await ctx.send(f"You do not have enough balance to place this bid. Your current balance is **{bal}**.")
                return

        active_auction = await self.get_auction_data(guild_config=guild_config, thread_id=ctx.channel.id)

        if not active_auction:
            await ctx.send("No active auction found in this channel (thread).")
            return

        previous_bidder = None
        if active_auction["current_bidder"]:
            previous_bidder = ctx.guild.get_member(active_auction["current_bidder"]) or await ctx.guild.fetch_member(active_auction["current_bidder"])
        current_bid = active_auction["current_bid"]

        if (current_bid is not None and amount <= current_bid) or amount < active_auction["min_bid"]:
            await ctx.send(f"Can't do that. Current bid is **{current_bid}**.")
            return
        if use_bank:
            await bank.withdraw_credits(ctx.author, amount)
            # Refund the previous bidder if they exist
            if previous_bidder and current_bid:
                await bank.deposit_credits(previous_bidder, current_bid)

        active_auction["current_bid"] = amount
        active_auction["current_bidder"] = ctx.author.id

        auction_message = self.get_cached_auction_message(active_auction["auction_id"]) 
        await ctx.send(f"Your bid of {active_auction['current_bid']} has been placed.")

        embed = auction_message.embeds[0]

        now = datetime.now(timezone.utc).timestamp()
        remaining_time = active_auction["end_timestamp"] - now
        if remaining_time <= 60:
            new_end_time = active_auction["end_timestamp"] + 60
            active_auction["end_timestamp"] = active_auction["end_timestamp"] + 60
            embed.set_field_at(0, name="Time Remaining", value=f"<t:{int(new_end_time)}:R>", inline=False)
            if active_auction["auction_id"] in self.auction_tasks:
                self.auction_tasks[active_auction["auction_id"]].cancel()
                del self.auction_tasks[active_auction["auction_id"]]
            task = asyncio.create_task(self.schedule_auction_end(auction_message, active_auction))
            self.auction_tasks[active_auction["auction_id"]] = task

        await self.update_auction_data(guild_config=guild_config, auction_data=active_auction)

        if active_auction["quick_sold"] is not None and amount >= active_auction["quick_sold"]:
            await self.close_auction(auction_message, active_auction["auction_id"])
            return

        embed.set_field_at(3, name="Current Bid", value=f"{active_auction['current_bid']}", inline=False)
        await auction_message.edit(embed=embed)
        
        if previous_bidder:
            if previous_bidder.id != active_auction["current_bidder"]:
                await self.try_dm(previous_bidder, f"-# You have been outbid in [#{active_auction['auction_id']}]({auction_message.jump_url})")

    @auction.command()
    @commands.is_owner()
    async def contract(self, ctx: commands.Context, member: discord.Member):
        """Make someone auctioneer."""
        if await self.config.member(member).auctioneer() == False:
            await self.config.member(member).auctioneer.set(True)
            await ctx.send(f"**{member.display_name}** is now an auctioneer. <:deal:972511367946981386>")
        else:
            await ctx.send("The user is already an auctioneer")

    @auction.command()
    async def resign(self, ctx: commands.Context, member: discord.Member = None):
        """Resign **an** auctioneer or resign **as an** auctioneer"""
        if (ctx.author == ctx.guild.owner or ctx.author.guild_permissions.administrator) and member:
            await self.config.member(member).auctioneer.set(False)
            await ctx.send(f"done.\n user: **{member.display_name}**")
        else:
            if await self.config.member(ctx.author).auctioneer() != True:
                await ctx.send("you are not an auctioneer.")
                return
            await ctx.send(f"resigning user: **{ctx.author.display_name}**\nyou sure?(yes/no)")
            def check(m):
                return (
                    m.author == ctx.author 
                    and m.channel == ctx.channel 
                    and m.content.lower() in {"yes", "no"})
            try:
                msg = await self.bot.wait_for("message", timeout=30.0, check=check)
                if msg.content.lower() == "yes":
                    await self.config.member(ctx.author).auctioneer.set(False)
                    await ctx.send(f"**{ctx.author.display_name}** resigned from being an auctioneer. <:deal:972511367946981386>")
                else:
                    await ctx.send("cancelled.")
            except asyncio.TimeoutError:
                await ctx.send("took too long to respond.")     
          
    @auction.command()
    async def list(self, ctx: commands.Context):
        """List all active auctions."""
        guild_config = self.config.guild(ctx.guild)
        auctions = await guild_config.auctions()
        
        if not auctions:
            await ctx.send("There are no active auctions in this server.")
            return

        auction_messages = [
            f"<#{auction['thread_id']}>" for auction in auctions
        ]
        auction_message = ", ".join(auction_messages)
        await ctx.send(auction_message)

    @auction.command()
    @commands.is_owner() 
    async def togglebank(self, ctx: commands.Context):
        """Enable or disable the use of Red's bank for auctions."""
        guild_config = self.config.guild(ctx.guild)
        use_bank = await guild_config.use_bank()
        new_status = not use_bank
        await guild_config.use_bank.set(new_status)
        status = "enabled" if new_status else "disabled"
        await ctx.send(f"Bank system has been **{status}** for auctions.")

    @auction.command()
    @commands.is_owner() 
    @commands.check(auction_initializing_check)
    async def forceremove(self, ctx: commands.Context, auction_id: int):
        """Removes an auction."""
        if not auction_id in self.auction_messages:
            await ctx.send(f"No auction found `#{auction_id}`.")
            return
        auction_message = self.get_cached_auction_message(auction_id)
        await self.close_auction(auction_message, auction_id, force_close=True)
        await ctx.send(f"Auction `#{auction_id}` remove.\n{auction_message.jump_url}")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        for auction_id, cached_message in list(self.auction_messages.items()):
            if cached_message.id == message.id:
                guild_config = self.config.guild(message.guild)
                await self.clean_up_auction(guild_config, auction_id)
                self.log.info(f"Auction #{auction_id} has been removed due to its message being deleted in guild: {message.guild.name} (ID: {message.guild.id}).")
                break
