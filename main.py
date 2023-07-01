import os
import asyncio
import discord
from utils.constants import PRIVILEGED_GUILDS, SENTIMENTS, DEFAULT_SENTIMENT, DEFAULT_QUOTA
from utils.database_utils import UserSettingsHandler
from utils.response_handler import ResponseHandler
from utils.prompt_completion import CompletionHandler
from utils.miscellaneous import capitalize_first_letter, time_until_refresh


class DiscordBot:
    SENTIMENTS_DISPLAY_NAMES = [f"{SENTIMENTS[sentiment]['display_name']} (Default)" if sentiment == DEFAULT_SENTIMENT else SENTIMENTS[sentiment]["display_name"] for sentiment in SENTIMENTS]

    def __init__(self, discord_token):
        self.discord_token = discord_token
        self.intents = discord.Intents.default()
        self.intents.message_content = True
        self.bot = discord.Bot(intents=self.intents)

    async def run_bot(self):

        @self.bot.command(name="help", description="Get to know more about this bot.")
        async def overview(ctx):
            await ctx.respond(embed=discord.Embed(
                description=f"Hello there! I'm a bot that uses AI to answer your questions. Just mention me at the start of your question and I'll try my best to help you. You can also change the tone of my replies by using the </sentiment:1123768896797814814> command. Available tones are: **{', '.join(self.SENTIMENTS_DISPLAY_NAMES)}.**\n\nPlease remember, each answer costs some tokens and you can only use up to **{DEFAULT_QUOTA} tokens** per day. To check how many tokens you have left, when they will be refilled, or what your current settings are, use the </settings:1123761931010977914> command.\n\nYou can also use the </images:1123775397838999624> command to decide if you want me to add images made by Adobe Firefly (an AI image generation tool) to my answers.",
                color=0xb4bcac
            ))

        @self.bot.command(name="settings", description="View your current settings and quota.")
        async def settings(ctx):
            user_settings = UserSettingsHandler(ctx.author.id)
            hours_until_refresh, minutes_until_refresh = time_until_refresh(user_settings.refresh_time)
            sentiment_display_name = SENTIMENTS[user_settings.sentiment]["display_name"]
            if user_settings.sentiment == DEFAULT_SENTIMENT:
                sentiment_display_name += " (Default)"
            use_legacy_text = "Yes" if user_settings.use_legacy else "No"
            allow_images_text = "Yes" if user_settings.allow_images else "No"

            embed_description = f"**{capitalize_first_letter(ctx.author.name)}**, here are your current settings and quota, if you wanna know more about them, use the </help:1123348801369952356> command:\n\n" \
                                f"**Remaining quota:** {max(user_settings.quota, 0)}\n" \
                                f"**Quota refresh in:** {hours_until_refresh}h {minutes_until_refresh}min\n" \
                                f"**Selected sentiment:** {sentiment_display_name}\n" \
                                f"**Use legacy model:** {use_legacy_text}\n" \
                                f"**Allow image attachments:** {allow_images_text}"

            await ctx.respond(embed=discord.Embed(description=embed_description, color=0xb4bcac))

        @self.bot.command(name="sentiment", description="Change the tone of the bot's replies.")
        async def sentiment(ctx, sentiment: discord.Option(str, name="sentiment", description="The sentiment you want the bot to use.", choices=self.SENTIMENTS_DISPLAY_NAMES)):
            user_settings = UserSettingsHandler(ctx.author.id)
            for key, value in SENTIMENTS.items():
                if value["display_name"] == sentiment.removesuffix(" (Default)"):
                    user_settings.sentiment = key
                    break

            sentiment_display_name = SENTIMENTS[user_settings.sentiment]["display_name"]
            if user_settings.sentiment == DEFAULT_SENTIMENT:
                sentiment_display_name += " (Default)"

            await ctx.respond(content=f"**{capitalize_first_letter(ctx.author.name)}**, your selected sentiment has been changed to **\"{sentiment_display_name}\"**.")

        @self.bot.command(name="legacy", description="Toggle the use of the legacy model.")
        async def legacy(ctx):
            user_settings = UserSettingsHandler(ctx.author.id)
            user_settings.use_legacy = int(not user_settings.use_legacy)
            use_legacy_text = "enabled" if user_settings.use_legacy else "disabled"
            await ctx.respond(content=f"**{capitalize_first_letter(ctx.author.name)}**, you have {use_legacy_text} the legacy model.")

        @self.bot.command(name="images", description="Toggle the use of images in the bot's replies.")
        async def images(ctx):
            user_settings = UserSettingsHandler(ctx.author.id)
            user_settings.allow_images = int(not user_settings.allow_images)
            allow_images_text = "enabled" if user_settings.allow_images else "disabled"
            await ctx.respond(content=f"**{capitalize_first_letter(ctx.author.name)}**, you have {allow_images_text} image attachments.")

        @self.bot.event
        async def on_message(message: discord.Message):
            if (f"<@{self.bot.user.id}>" in message.content or message.guild is None) and not message.author.bot:
                prompt = message.content.replace(f"<@{self.bot.user.id}>", "").strip()
                async with message.channel.typing():
                    if prompt:
                        if len(prompt) > 1200:
                            await ResponseHandler(message).send_response("Whoa, that's a lot of text, I can't be bothered to read that.")
                        else:
                            user_settings = UserSettingsHandler(message.author.id)
                            if user_settings.quota > 0 or message.guild is not None and message.guild.id in PRIVILEGED_GUILDS and not user_settings.use_legacy:
                                if not user_settings.use_legacy:
                                    completion, image_locations = await CompletionHandler(user_settings).complete_prompt(message, prompt)
                                    await ResponseHandler(message).send_response(completion, image_locations)
                                else:
                                    completion = await CompletionHandler(user_settings).complete_prompt_legacy(message, user_settings, prompt)
                                    await ResponseHandler(message).send_response(completion)
                            else:
                                hours_until_refresh, minutes_until_refresh = time_until_refresh(user_settings.refresh_time)
                                await ResponseHandler(message).send_response(f"**{capitalize_first_letter(message.author.name)}**, you have run out of tokens for today. Please try again in **{hours_until_refresh}h {minutes_until_refresh}min**.")
                    else:
                        await ResponseHandler(message).send_response("Hello there, I'm a divine being. Ask me anything, or use </help:1123348801369952356> to learn more.")

        await self.bot.start(self.discord_token)


if __name__ == "__main__":
    bot = DiscordBot(os.getenv("DISCORD_TOKEN"))
    loop = asyncio.get_event_loop()
    loop.create_task(bot.run_bot())
    loop.run_forever()
