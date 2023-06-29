import os
import asyncio
import discord
from utils.constants import PRIVILEGED_GUILDS, SENTIMENTS, DEFAULT_SENTIMENT, DEFAULT_QUOTA
from utils.database_utils import UserSettingsWrapper
from utils.response_handler import send_response
from utils.prompt_completion import prepare_prompt, complete_prompt, complete_prompt_legacy
from utils.image_generation import clear_image_cache
from utils.miscellaneous import capitalize_first_letter, time_until_refresh

TOKEN = os.getenv("DISCORD_TOKEN")
bot = discord.Bot()


async def run_bot():
    SENTIMENTS_DISPLAY_NAMES = [f"{SENTIMENTS[sentiment]['display_name']} (Default)" if sentiment == DEFAULT_SENTIMENT else SENTIMENTS[sentiment]["display_name"] for sentiment in SENTIMENTS]

    @bot.command(name="help", description="Get to know more about this bot.")
    async def overview(ctx):
        await ctx.respond(embed=discord.Embed(
            description=f"Hello there! I'm a bot that uses AI to answer your questions. Just mention me at the start of your question and I'll try my best to help you. You can also change the tone of my replies by using the </sentiment:1071764449922404412> command. Available tones are: **{', '.join(SENTIMENTS_DISPLAY_NAMES)}.**\n\nPlease remember, each answer costs some tokens and you can only use up to **{DEFAULT_QUOTA} tokens** per day. To check how many tokens you have left and when they will be refilled, use the </quota:1071568078099460127> command.\n\nYou can also use the </images:1100157891941511360> command to decide if you want me to add images made by Adobe Firefly (an AI image generation tool) to my answers.",
            color=0xb4bcac
        ))

    @bot.command(name="settings", description="View your current settings and quota.")
    async def settings(ctx):
        user_settings = UserSettingsWrapper(ctx.author.id)
        hours_until_refresh, minutes_until_refresh = time_until_refresh(user_settings.refresh_time)
        sentiment_display_name = SENTIMENTS[user_settings.sentiment]["display_name"]
        if user_settings.sentiment == DEFAULT_SENTIMENT:
            sentiment_display_name += " (Default)"
        use_legacy_text = "Yes" if user_settings.use_legacy else "No"
        allow_images_text = "Yes" if user_settings.allow_images else "No"

        embed_description = f"**{capitalize_first_letter(ctx.author.name)}**, here are your current settings and quota, if you wanna know more about them, use the </help:1123348801369952356> command:\n\n" \
                            f"**Remaining quota:** {user_settings.quota}\n" \
                            f"**Quota refresh in:** {hours_until_refresh}h, {minutes_until_refresh}min\n" \
                            f"**Selected sentiment:** {sentiment_display_name}\n" \
                            f"**Use legacy model:** {use_legacy_text}\n" \
                            f"**Allow image attachments:** {allow_images_text}"

        await ctx.respond(embed=discord.Embed(description=embed_description, color=0xb4bcac))

    @bot.command(name="sentiment", description="Change the tone of the bot's replies.")
    async def sentiment(ctx, sentiment: discord.Option(str, name="sentiment", description="The sentiment you want the bot to use.", choices=SENTIMENTS_DISPLAY_NAMES)):
        user_settings = UserSettingsWrapper(ctx.author.id)
        for key, value in SENTIMENTS.items():
            if value["display_name"] == sentiment:
                user_settings.sentiment = key
                break
        await ctx.respond(content=f"**{capitalize_first_letter(ctx.author.name)}**, your selected sentiment has been changed to **\"{SENTIMENTS[user_settings.sentiment]['display_name']}\"**.")
    
    @bot.command(name="legacy", description="Toggle the use of the legacy model.")
    async def legacy(ctx):
        user_settings = UserSettingsWrapper(ctx.author.id)
        user_settings.use_legacy = int(not user_settings.use_legacy)
        use_legacy_text = "enabled" if user_settings.use_legacy else "disabled"
        await ctx.respond(content=f"**{capitalize_first_letter(ctx.author.name)}**, you have {use_legacy_text} the legacy model.")

    @bot.command(name="images", description="Toggle the use of images in the bot's replies.")
    async def images(ctx):
        user_settings = UserSettingsWrapper(ctx.author.id)
        user_settings.allow_images = int(not user_settings.allow_images)
        allow_images_text = "enabled" if user_settings.allow_images else "disabled"
        await ctx.respond(content=f"**{capitalize_first_letter(ctx.author.name)}**, you have {allow_images_text} image attachments.")

    @bot.event
    async def on_message(message: discord.Message):
        if f"<@{bot.user.id}>" in message.content or message.guild is None and message.author.id != bot.user.id:
            prompt = message.content.replace(f"<@{bot.user.id}>", "").strip()
            async with message.channel.typing():
                if prompt:
                    if len(prompt) > 1200:
                        await send_response(message, "Whoa, that's a lot of text, I can't be bothered to read that.")
                    else:
                        user_settings = UserSettingsWrapper(message.author.id)
                        if user_settings.quota > 0 or message.guild is not None and message.guild.id in PRIVILEGED_GUILDS and not user_settings.use_legacy:
                            preprocessed_prompt = prepare_prompt(message, user_settings, prompt)

                            if not user_settings.use_legacy:
                                completion, image_locations = await complete_prompt(message, user_settings, preprocessed_prompt)
                                await send_response(message, completion, image_locations)
                                clear_image_cache(message.id, len(image_locations))
                            else:
                                completion = await complete_prompt_legacy(message, user_settings, preprocessed_prompt)
                                await send_response(message, completion)
                        else:
                            hours_until_refresh, minutes_until_refresh = time_until_refresh(user_settings.refresh_time)
                            await send_response(message, f"**{capitalize_first_letter(message.author.name)}**, you have run out of tokens for today. Please try again in **{hours_until_refresh}h {minutes_until_refresh}min**.")
                else:
                    await send_response(message, "Hello there, I'm a divine being. Ask me anything, or use </help:1123348801369952356> to learn more.")

    await bot.start(TOKEN)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(run_bot())
    loop.run_forever()
