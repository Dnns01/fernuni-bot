import asyncio
import datetime
import json
import os
import re

import discord
from discord.ext import tasks, commands


def is_valid_time(time):
    return re.match(r"^\d+[mhd]?$", time)


def to_minutes(time):
    if time[-1:] == "m":
        return int(time[:-1])
    elif time[-1:] == "h":
        h = int(time[:-1])
        return h * 60
    elif time[-1:] == "d":
        d = int(time[:-1])
        h = d * 24
        return h * 60

    return int(time)


class AppointmentsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.fmt = os.getenv("DISCORD_DATE_TIME_FORMAT")
        self.timer.start()
        self.appointments = {}
        self.app_file = os.getenv("DISCORD_APPOINTMENTS_FILE")
        self.load_appointments()

    def load_appointments(self):
        """ Loads all appointments from APPOINTMENTS_FILE """

        appointments_file = open(self.app_file, mode='r')
        self.appointments = json.load(appointments_file)

    @tasks.loop(minutes=1)
    async def timer(self):
        delete = []

        for channel_id, channel_appointments in self.appointments.items():
            channel = None
            for message_id, appointment in channel_appointments.items():
                now = datetime.datetime.now()
                date_time = datetime.datetime.strptime(appointment["date_time"], self.fmt)
                remind_at = date_time - datetime.timedelta(minutes=appointment["reminder"])

                if now >= remind_at:
                    try:
                        channel = await self.bot.fetch_channel(int(channel_id))
                        message = await channel.fetch_message(int(message_id))
                        reactions = message.reactions
                        diff = int(round(((date_time - now).total_seconds() / 60), 0))
                        answer = f"Benachrichtigung!\nDer Termin \"{appointment['title']}\" ist "

                        if appointment["reminder"] > 0 and diff > 0:
                            answer += f"in {diff} Minuten fällig."
                            appointment["reminder"] = 0
                        else:
                            answer += f"jetzt fällig. :loudspeaker: "
                            delete.append(message_id)

                        answer += f"\n"
                        for reaction in reactions:
                            if reaction.emoji == "👍":
                                async for user in reaction.users():
                                    if user != self.bot.user:
                                        answer += f"<@!{str(user.id)}>"

                        await channel.send(answer)

                        if str(message.id) in delete:
                            await message.delete()
                    except discord.errors.NotFound:
                        delete.append(message_id)

            if len(delete) > 0:
                for key in delete:
                    channel_appointment = channel_appointments.get(key)
                    if channel_appointment:
                        if channel_appointment["recurring"]:
                            recurring = channel_appointment["recurring"]
                            date_time_str = channel_appointment["date_time"]
                            date_time = datetime.datetime.strptime(date_time_str, self.fmt)
                            new_date_time = date_time + datetime.timedelta(minutes=recurring)
                            new_date_time_str = new_date_time.strftime(self.fmt)
                            splitted_new_date_time_str = new_date_time_str.split(" ")
                            await self.add_appointment(channel, channel_appointment["author_id"],
                                                       splitted_new_date_time_str[0],
                                                       splitted_new_date_time_str[1],
                                                       str(channel_appointment["reminder"]),
                                                       channel_appointment["title"],
                                                       str(channel_appointment["recurring"]))
                        channel_appointments.pop(key)
                self.save_appointments()

    @timer.before_loop
    async def before_timer(self):
        await asyncio.sleep(60 - datetime.datetime.now().second)

    @commands.command(name="add-appointment")
    async def cmd_add_appointment(self, ctx, date, time, reminder, title, recurring=None):
        await self.add_appointment(ctx.channel, ctx.author.id, date, time, reminder, title, recurring)

    async def add_appointment(self, channel, author_id, date, time, reminder, title, recurring=None):
        """ Add appointment to a channel """

        try:
            date_time = datetime.datetime.strptime(f"{date} {time}", self.fmt)
        except ValueError:
            await channel.send("Fehler! Ungültiges Datums und/oder Zeit Format!")
            return

        if not is_valid_time(reminder):
            await channel.send("Fehler! Benachrichtigung in ungültigem Format!")
            return
        else:
            reminder = to_minutes(reminder)

        if recurring:
            if not is_valid_time(recurring):
                await channel.send("Fehler! Wiederholung in ungültigem Format!")
                return
            else:
                recurring = to_minutes(recurring)

        embed = discord.Embed(title="Neuer Termin hinzugefügt!",
                              description=f"Wenn du eine Benachrichtigung zum Beginn des Termins"
                                          f"{f', sowie {reminder} Minuten vorher, ' if reminder > 0 else f''} "
                                          f"erhalten möchtest, reagiere mit :thumbsup: auf diese Nachricht.",
                              color=19607)

        embed.add_field(name="Titel", value=title, inline=False)
        embed.add_field(name="Startzeitpunkt", value=f"{date_time.strftime(self.fmt)}", inline=False)
        if reminder > 0:
            embed.add_field(name="Benachrichtigung", value=f"{reminder} Minuten vor dem Start", inline=False)
        if recurring:
            embed.add_field(name="Wiederholung", value=f"Alle {recurring} Minuten", inline=False)

        message = await channel.send(embed=embed)
        await message.add_reaction("👍")
        await message.add_reaction("🗑️")

        if str(channel.id) not in self.appointments:
            self.appointments[str(channel.id)] = {}

        channel_appointments = self.appointments.get(str(channel.id))
        channel_appointments[str(message.id)] = {"date_time": date_time.strftime(self.fmt), "reminder": reminder,
                                                 "title": title, "author_id": author_id, "recurring": recurring}

        self.save_appointments()

    @commands.command(name="appointments")
    async def cmd_appointments(self, ctx):
        """ List (and link) all Appointments in the current channel """

        if str(ctx.channel.id) in self.appointments:
            channel_appointments = self.appointments.get(str(ctx.channel.id))
            answer = f'Termine dieses Channels:\n'
            delete = []

            for message_id, appointment in channel_appointments.items():
                try:
                    message = await ctx.channel.fetch_message(int(message_id))
                    answer += f'{appointment["date_time"]}: {appointment["title"]} => ' \
                              f'{message.jump_url}\n'
                except discord.errors.NotFound:
                    delete.append(message_id)

            if len(delete) > 0:
                for key in delete:
                    channel_appointments.pop(key)
                self.save_appointments()

            await ctx.channel.send(answer)
        else:
            await ctx.send("Für diesen Channel existieren derzeit keine Termine")

    def save_appointments(self):
        appointments_file = open(self.app_file, mode='w')
        json.dump(self.appointments, appointments_file)

    async def handle_reactions(self, payload):
        channel = await self.bot.fetch_channel(payload.channel_id)
        channel_appointments = self.appointments.get(str(payload.channel_id))
        if channel_appointments:
            appointment = channel_appointments.get(str(payload.message_id))
            if appointment:
                if payload.user_id == appointment["author_id"]:
                    message = await channel.fetch_message(payload.message_id)
                    await message.delete()
                    channel_appointments.pop(str(payload.message_id))

        self.save_appointments()

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if payload.user_id == self.bot.user.id:
            return

        if payload.emoji.name in ["🗑️"]:
            channel = await self.bot.fetch_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
            if len(message.embeds) > 0 and message.embeds[0].title == "Neuer Termin hinzugefügt!":
                await self.handle_reactions(payload)
