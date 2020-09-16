import discord

OPTIONS = ["\u0031\u20E3", "\u0032\u20E3", "\u0033\u20E3", "\u0034\u20E3", "\u0035\u20E3", "\u0036\u20E3",
           "\u0037\u20E3", "\u0038\u20E3", "\u0039\u20E3", "\u0040\u20E3"]


class Poll:

    def __init__(self, bot, question=None, answers=None, author=None, message=None):
        self.bot = bot
        self.question = question
        self.answers = answers
        self.author = author

        if message:
            self.message = message
            self.answers = []
            embed = message.embeds[0]
            self.author = embed.fields[0].value[3:-1]
            self.question = embed.description
            for i in range(2, len(embed.fields)):
                self.answers.append(embed.fields[i].value)

    async def send_poll(self, channel, result=False):
        option_ctr = 0
        title = "Umfrage"

        if result:
            title += " Ergebnis"

        if len(self.answers) > 10:
            await channel.send(
                "Fehler beim Erstellen der Umfrage! Es werden derzeit nicht mehr als 10 Optionen unterstützt!")
            return

        embed = discord.Embed(title=title, description=self.question)
        embed.add_field(name="Erstellt von", value=f'<@!{self.author}>', inline=False)
        embed.add_field(name="\u200b", value="\u200b", inline=False)

        for i in range(0, len(self.answers)):
            name = f'{OPTIONS[i]}'
            value = f'{self.answers[i]}'

            if result:
                reaction = self.get_reaction(OPTIONS[i])
                if reaction:
                    name += f' : {reaction.count - 1}'
                    value += f'\nStimmen: '

                    async for user in reaction.users():
                        if self.bot.user == user:
                            continue

                        value += f'<@!{str(user.id)}> '

            embed.add_field(name=name, value=value, inline=False)
            option_ctr += 1

        message = await channel.send("", embed=embed)

        if not result:
            for i in range(0, len(self.answers)):
                await message.add_reaction(OPTIONS[i])

            await message.add_reaction("🗑️")
            await message.add_reaction("🛑")

    async def close_poll(self):
        await self.send_poll(self.message.channel, result=True)
        await self.delete_poll()

    async def delete_poll(self):
        await self.message.delete()

    def get_reaction(self, reaction):
        if self.message:
            reactions = self.message.reactions

            for react in reactions:
                if react.emoji == reaction:
                    return react
