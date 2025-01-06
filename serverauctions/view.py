from __future__ import annotations

import discord
import asyncio
from redbot.core import commands
from datetime import datetime, timezone, timedelta

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .auction import ServerAuctions

class AuctionSetup(discord.ui.View):
    def __init__(self, ctx: commands.Context, embed: discord.Embed, auction_data: dict, auc: ServerAuctions):
        super().__init__(timeout=300)
        self.ctx = ctx
        self.auction_data = auction_data
        self.embed = embed
        self.auc = auc
        self.modal_data = {"min_bid": 1}

    @discord.ui.button(label='Configure', style=discord.ButtonStyle.green)
    async def configure(self, interaction: discord.Interaction, button: discord.ui.Button):
        auc_modal = AuctionInfo(interaction, interaction.message, self.modal_data)
        await interaction.response.send_modal(auc_modal)
        await auc_modal.wait()

        if any(value <= 0 for value in [auc_modal.time_period, auc_modal.quick_sold, auc_modal.minimum_bid] if value is not None):
            return
        elif auc_modal.time_period == None:
            return

        self.modal_data["time_period"] = auc_modal.time_period
        self.modal_data["name"] = auc_modal.name
        self.modal_data["description"] = auc_modal.description
        self.modal_data["quick_sold"] = auc_modal.quick_sold
        self.modal_data["min_bid"] = auc_modal.minimum_bid
        
        end_time = datetime.now(timezone.utc) + timedelta(minutes=auc_modal.time_period)
        end_timestamp = int(end_time.timestamp())
        self.embed.clear_fields()
        self.embed.title = f"#??? - {auc_modal.name}"
        self.embed.description = auc_modal.description
        self.embed.add_field(name="Time Remaining", value=f"<t:{end_timestamp}:R>", inline=False)
        self.auction_data["end_timestamp"] = end_timestamp
        self.embed.add_field(name="Quick Sold Amount", value=auc_modal.quick_sold, inline=False)
        self.auction_data["quick_sold"] = auc_modal.quick_sold
        self.embed.add_field(name="Min Bid", value=auc_modal.minimum_bid, inline=False)
        self.auction_data["min_bid"] = auc_modal.minimum_bid
        self.embed.add_field(name="Current Bid", value=f'{self.auction_data["current_bid"]}', inline=False)
        self.embed.set_footer(text=f"Host: {interaction.user.display_name}")
        await interaction.message.edit(embed=self.embed, view=self)
        self.children[1].disabled = False
        await interaction.message.edit(embed=self.embed, view=self) 


    @discord.ui.button(label='Confirm', style=discord.ButtonStyle.green, disabled=True)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
       
        guild_config = self.auc.config.guild(self.ctx.guild)
        current_auction_count = await guild_config.auction_count()
        await guild_config.auction_count.set(current_auction_count + 1)
        self.auction_data["auction_id"] = current_auction_count + 1
        self.embed.title = self.embed.title.replace('???', str(self.auction_data['auction_id']))
        auc_thread = await self.ctx.channel.create_thread(name=self.embed.title, type=discord.ChannelType.public_thread)
        auction_message = await auc_thread.send(embed=self.embed)
        await auction_message.pin()

        self.auc.cache_auction_message(self.auction_data["auction_id"], auction_message)

        self.auction_data["thread_id"] = auc_thread.id
        self.auction_data["message_id"] = auction_message.id
        async with guild_config.auctions() as auctions:
            auctions.append(self.auction_data)

        task = asyncio.create_task(self.auc.schedule_auction_end(auction_message, self.auction_data))
        self.auc.auction_tasks[self.auction_data["auction_id"]] = task

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.red)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.delete()
        self.stop()
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.ctx.author:
            await interaction.response.send_message("You cannot use this button :(", ephemeral=True)
            return False
        else:
            return True
        
    async def on_timeout(self):
        self.stop()

class NotWholeNumber(Exception):
    pass

class AuctionInfo(discord.ui.Modal):
    def __init__(self, interaction: discord.Interaction, message: discord.Message, auction_data: dict = None):
        super().__init__(title="Auction Info", custom_id=f"auction_info_{message.id}")
        self.interaction = interaction
        self.message = message
        self.auction_data = auction_data
        self.name = None
        self.description = None
        self.time_period = None
        self.quick_sold = None
        self.minimum_bid = 1

        self.name_input.default = auction_data.get('name', '')
        self.description_input.default = auction_data.get('description', '')
        self.time_period_input.default = str(auction_data.get('time_period', '')) if auction_data.get('time_period') is not None else ''
        self.quick_sold_input.default = str(auction_data.get('quick_sold', '')) if auction_data.get('quick_sold') is not None else ''
        self.minimum_bid_input.default = str(auction_data.get('min_bid', ''))

    name_input = discord.ui.TextInput(
        label='Name',
        placeholder='Enter the name of the thing you want to auction...',
        required=True,
        max_length=50,
    )

    description_input = discord.ui.TextInput(
        label='Description',
        style=discord.TextStyle.long,
        placeholder='Enter the description of the thing...',
        required=False,
        max_length=1500,
    )

    time_period_input = discord.ui.TextInput(
        label='Time Period(Minutes)',
        placeholder='Enter the time period of the auction in minutes(integer)...',
        required=True,
        max_length=7,
    )

    quick_sold_input = discord.ui.TextInput(
        label='Quick Sold Amount(upper limit of bid)',
        placeholder='Enter the maximum bid amount(intger)...',
        required=False,
        max_length=30,
    )

    minimum_bid_input = discord.ui.TextInput(
        label='Minimum Bid Amount(default 1)',
        placeholder='Enter the minimum bid amount(intger)...',
        required=False,
        max_length=30,
    )


    async def on_submit(self, interaction: discord.Interaction):
        self.name = self.name_input.value
        self.description = self.description_input.value
        try:
            self.time_period = int(self.time_period_input.value)
            self.quick_sold = int(self.quick_sold_input.value) if self.quick_sold_input.value else None
            self.minimum_bid = int(self.minimum_bid_input.value) if self.minimum_bid_input.value else 1
            if any(x is not None and x <= 0 for x in [self.time_period, self.quick_sold, self.minimum_bid]):
                raise NotWholeNumber("Values must be greater than zero.")
        except NotWholeNumber as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return
        except ValueError:
            await interaction.response.send_message("Invalid Input", ephemeral=True)
            return
        await interaction.response.defer()

