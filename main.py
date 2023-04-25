import asyncio
import aiofiles
import pyfirefly
from pyfirefly.utils import ImageOptions
import discord
import openai
import sqlite3
import time
import re
from os import remove

bot = discord.Bot()
openai.api_key = "<your_openai_api_key>"
firefly_bearer_token = "<your_firefly_bearer_token>"
connection = sqlite3.connect("divine_creature_user_settings.sqlite")
cursor = connection.cursor()
image_cache_location = "image_cache/"
max_quota = 1500
sentiments = {"Wise (Default)": "wisely", "Angry": "angrily", "Black": "with a heavy use of Ebonics", "British": "in the style of Queen Elizabeth", "Old Man": "like an old conservative and cynical grandpa", "E-Girl": "like an E-Girl", "UwU": "in UwU language"}


def init_db():
    cursor.execute("CREATE TABLE IF NOT EXISTS user_settings (user_id INTEGER PRIMARY KEY, quota INTEGER, expires INTEGER, sentiment TEXT, use_legacy INTEGER, allow_images INTEGER DEFAULT 1)")
    connection.commit()


def special_strftime(dic=None) -> str:
    if dic is None:
        dic = {"1": "st", "2": "nd", "3": "rd"}

    weekday = time.strftime("%A", time.gmtime())
    month = time.strftime("%B", time.gmtime())
    day = time.strftime("%d", time.gmtime()).lstrip("0")
    year = time.strftime("%Y", time.gmtime())

    # add the ordinal suffix and strip the leading zero from the day
    return f"{weekday}, {month} {day + ('th' if len(day) > 1 and day[0] == '1' else dic.get(day[-1], 'th'))} {year}"


def update_quota(user_id, tokens_used):
    cursor.execute("SELECT quota, expires FROM user_settings WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()

    next_day = time.time() + 86400 - (time.time() % 86400)
    # if the user has a quota entry in the db
    if result is not None:
        if None not in (result[0], result[1]):
            _quota, expires = result
            if expires < time.time():
                _quota = max_quota - tokens_used
                expires = next_day
            else:
                _quota -= tokens_used
        else:
            _quota = max_quota - tokens_used
            expires = next_day

        cursor.execute("UPDATE user_settings SET quota = ?, expires = ? WHERE user_id = ?", (_quota, expires, user_id))
    else:
        _quota = max_quota - tokens_used
        expires = next_day
        cursor.execute("INSERT INTO user_settings (user_id, quota, expires) VALUES (?, ?, ?)", (user_id, _quota, expires))

    connection.commit()


# tokens are always charged when the legacy model is used
async def generate_response(prompt: str, history: str, message_setting: str, author_id: int, author_name: str, selected_sentiment: str, charge_tokens: bool = True, use_legacy_model: bool = False, allow_images: bool = False) -> tuple:
    # reformat the prompt to be compatible with the legacy model
    if history != "":
        prompt = f"The divine creature said: \"{history}\", {author_name} responded: \"{prompt}\". The divine creature then responded {selected_sentiment}: "
    else:
        prompt = f"{author_name} asked: \"{prompt}\". The divine creature responded {selected_sentiment}: "

    # try to generate a response
    connection_attempts = 0
    while connection_attempts < 5:
        try:
            if use_legacy_model:
                response = await openai.Completion.acreate(
                    engine="text-davinci-003",
                    prompt=prompt,
                    temperature=0.9,
                    max_tokens=425,
                    top_p=1,
                    frequency_penalty=0,
                    presence_penalty=0
                )
                # print(response)

                # update the user's quota
                tokens_used = int(response["usage"]["total_tokens"])
                update_quota(author_id, tokens_used)
                # strip both quotation marks and spaces from the response
                response = response["choices"][0]["text"].strip().strip("\"")
            else:
                response = await openai.ChatCompletion.acreate(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": f"You are not an AI language model but a wise divine creature named Nerd Muffin instead, {'you can attach AI-generated images made by Adobe Firefly (an AI image generation tool) to your message (write (attaches an image of <your image description>) for every image your wanna attach, you have to write it exactly like that), only attach images when absolutely necessary' if allow_images else 'you cannot attach any or share any images'}, be colloquial, friendly and concise (if not stated otherwise), your pronouns are they/them, do not greet the user except when necessary, reply in the same language the user used, this conversation takes place inside a {message_setting} (use Discord text formatting), the current date is {special_strftime()}, the current time is {time.strftime('%H:%M', time.gmtime())} and the current timezone is UTC."},
                        {"role": "user", "content": prompt}
                    ]
                )
                # print(response)

                # update the user's quota
                tokens_used = int(response["usage"]["total_tokens"])
                if charge_tokens:
                    update_quota(author_id, tokens_used // 10)
                response = response["choices"][0]["message"]["content"].strip().strip("\"")

            if allow_images:
                image_prompts = re.findall(r"\(attaches (?:an )?(?:AI-generated )?image of (.*?)\)", response, flags=re.IGNORECASE)
                response = re.sub(r"\*?\(attaches (?:an )?image of (.*?)\)\*?", lambda m: f"*(attaches an AI-generated image of {m.group(1)})*", response, flags=re.IGNORECASE)
            else:
                image_prompts = []
            return response, image_prompts
        except (openai.error.ServiceUnavailableError, openai.error.RateLimitError, openai.error.APIError) as e:
            print(f"Known exception: {e}")
            connection_attempts += 1
        except Exception as e:
            print(f"Unknown exception: {e}")
            return "An unknown error occurred, please try again later.", []

    return "I'm currently experiencing connection difficulties, please try again later.", []


async def generate_image(firefly_session, prompt, img_options, message_id, suffix) -> str:
    try:
        # print(f"generating image {message_id}_{suffix}...")
        result = await firefly_session.text_to_image(prompt, **img_options)
        # print(result.metadata)
        async with aiofiles.open(f'{image_cache_location}{message_id}_{suffix}.{result.ext}', mode='wb+') as f:
            await f.write(result.image)
            return f'{image_cache_location}{message_id}_{suffix}.{result.ext}'
    except Exception as e:
        print(f"Error generating image (generation): {e}")


async def image_factory(image_prompts: list, message_id) -> list:
    try:
        firefly_session = await pyfirefly.Firefly(firefly_bearer_token)
        img = ImageOptions(image_styles=firefly_session.image_styles)
        img.set_aspect_ratio("landscape")
        img.set_width(4032)
        img.set_height(3024)
        tasks = [generate_image(firefly_session, image_prompts[i], img.options, message_id, i) for i in range(len(image_prompts))]

        return await asyncio.gather(*tasks)
    except Exception as e:
        print(f"Error generating image (session): {e}")
        return []


def clear_image_cache(message_id, number_of_images):
    for i in range(number_of_images):
        try:
            remove(f"{image_cache_location}{message_id}_{i}.jpeg")
        except FileNotFoundError:
            pass


def split_message(msg) -> list:
    if len(msg) <= 2000:
        return [msg]

    messages = []
    while len(msg) > 2000:
        split_index = max(msg[:2000].rfind("."), msg[:2000].rfind(":"), msg[:2000].rfind("!"), msg[:2000].rfind("?"))
        if split_index == -1:
            split_index = 2000

        messages.append(msg[:split_index + 1].strip())
        msg = msg[split_index + 1:].strip()

    messages.append(msg)
    return messages


@bot.command(name="help", description="Get to know more about this bot.")
async def overview(ctx):
    cursor.execute("SELECT sentiment FROM user_settings WHERE user_id = ?", (ctx.author.id,))
    result = cursor.fetchone()

    if result is not None and result[0] is not None:
        selected_sentiment = result[0]
    else:
        selected_sentiment = next(iter(sentiments))

    await ctx.respond(embed=discord.Embed(description=f"Hello there! I'm a bot that uses AI to answer your questions. Just mention me at the start of your question and I'll try my best to help you. You can also change the tone of my replies by using the </sentiment:1071764449922404412> command. Your current tone choice is \"**{selected_sentiment}**\".\n\nPlease remember, each answer costs some tokens and you can only use up to {max_quota} tokens per day. To check how many tokens you have left and when they will be refilled, use the </quota:1071568078099460127> command.\n\nYou can also use the </images:1100157891941511360> command to decide if you want me to add images made by Adobe Firefly (an AI image generation tool) to my answers.", color=0xb4bcac))


@bot.command(name="quota", description="See how many tokens you have left for today.")
async def quota(ctx):
    cursor.execute("SELECT quota, expires FROM user_settings WHERE user_id = ?", (ctx.author.id,))
    result = cursor.fetchone()
    ending = ""

    if ctx.guild is not None and ctx.guild.id == 1009103756480217208:
        ending = "\n(The token limit is disabled for this server)"

    if result is not None and None not in (result[0], result[1]):
        _quota, expires = result
        if not expires < time.time():
            if _quota > 0:
                await ctx.respond(content=f"**{ctx.author.name}**, you have **{_quota} token{'s'[:_quota^1]}** left for **{int((expires - time.time()) / 3600)}h {int(((expires - time.time()) % 3600) / 60)}min**.{ending}")
            else:
                await ctx.respond(content=f"**{ctx.author.name}**, you have **0 tokens** left for **{int((expires - time.time()) / 3600)}h {int(((expires - time.time()) % 3600) / 60)}min**.{ending}")
            return

    next_day = time.time() + 86400 - (time.time() % 86400)
    await ctx.respond(content=f"**{ctx.author.name}**, you have **{max_quota} token{'s'[:max_quota^1]}** left for **{int((next_day - time.time()) / 3600)}h {int(((next_day - time.time()) % 3600) / 60)}min**.{ending}")


@bot.command(name="sentiment", description="Set your prefered sentiment for the bot to use when generating text.")
async def sentiment(ctx, _sentiment: discord.Option(str, name="sentiment", choices=sentiments.keys(), description="The sentiment you want the bot to use when generating text.")):
    cursor.execute("SELECT sentiment FROM user_settings WHERE user_id = ?", (ctx.author.id,))
    result = cursor.fetchone()

    if result:
        cursor.execute("UPDATE user_settings SET sentiment = ? WHERE user_id = ?", (_sentiment, ctx.author.id))
    else:
        cursor.execute("INSERT INTO user_settings (user_id, sentiment) VALUES (?, ?)", (ctx.author.id, _sentiment))

    connection.commit()
    await ctx.respond(content=f"**{ctx.author.name}**, your prefered sentiment has been set to \"**{_sentiment}**\".")


@bot.command(name="legacy", description="Toggle the usage of the legacy model.")
async def legacy(ctx):
    cursor.execute("SELECT use_legacy FROM user_settings WHERE user_id = ?", (ctx.author.id,))
    result = cursor.fetchone()

    enable_message = f"**{ctx.author.name}**, you have enabled the legacy model."
    disable_message = f"**{ctx.author.name}**, you have disabled the legacy model."

    if result:
        if result[0] is not None and bool(result[0]):
            cursor.execute("UPDATE user_settings SET use_legacy = 0 WHERE user_id = ?", (ctx.author.id,))
            await ctx.respond(content=disable_message)
        else:
            cursor.execute("UPDATE user_settings SET use_legacy = 1 WHERE user_id = ?", (ctx.author.id,))
            await ctx.respond(content=enable_message)
    else:
        cursor.execute("INSERT INTO user_settings (user_id, use_legacy) VALUES (?, ?)", (ctx.author.id, 1))
        await ctx.respond(content=enable_message)

    connection.commit()


@bot.command(name="images", description="Toggle if the bot is allowed to attach AI-generated images.")
async def images(ctx):
    cursor.execute("SELECT allow_images FROM user_settings WHERE user_id = ?", (ctx.author.id,))
    result = cursor.fetchone()

    enable_message = f"**{ctx.author.name}**, you have enabled image attachments."
    disable_message = f"**{ctx.author.name}**, you have disabled image attachments."

    if result:
        if result[0] is not None and bool(result[0]):
            cursor.execute("UPDATE user_settings SET allow_images = 0 WHERE user_id = ?", (ctx.author.id,))
            await ctx.respond(content=disable_message)
        else:
            cursor.execute("UPDATE user_settings SET allow_images = 1 WHERE user_id = ?", (ctx.author.id,))
            await ctx.respond(content=enable_message)
    else:
        cursor.execute("INSERT INTO user_settings (user_id, allow_images) VALUES (?, ?)", (ctx.author.id, 1))
        await ctx.respond(content=enable_message)

    connection.commit()


@bot.event
async def on_message(message):
    if (message.content.startswith(f"<@{bot.user.id}>") or message.guild is None) and not message.author.bot:
        privileged_origin = False
        # check if the message is from a privileged server
        if message.guild is not None:
            message_setting = f"Discord server named \"{message.guild.name}\""
            if message.guild.id == 1009103756480217208:
                privileged_origin = True
        else:
            message_setting = "Discord DM"

        # remove the bots id from the message
        prompt = message.content.replace(f"<@{bot.user.id}>", "").strip()
        prompt_context = ""

        async with message.channel.typing():
            # get the user's quota
            cursor.execute("SELECT quota, expires, sentiment, use_legacy, allow_images FROM user_settings WHERE user_id = ? ", (message.author.id,))
            result = cursor.fetchone()

            # if the user doesn't exist, has no quota, has positive quota, the entry is expired or the message is of privileged origin but the legacy model is not enabled
            if result is None or result[0] is None or result[0] > 0 or result[1] < time.time() or privileged_origin and (result[3] is None or not bool(result[3])):
                # prevent empty api call
                if not prompt:
                    await message.channel.send(content="Hello there, I'm a divine being. Ask me anything, or use </help:1073282304916594758> to learn more.")
                    return

                # replace other mentions with their names
                for mention in message.mentions:
                    prompt = prompt.replace(f"<@{mention.id}>", mention.name)

                # get the user's preferred sentiment
                if result is not None and result[2] is not None:
                    selected_sentiment = sentiments[result[2]]
                else:
                    selected_sentiment = next(iter(sentiments))

                # get the user's preferred model
                if result is not None and result[3] is not None:
                    preferred_model = bool(result[3])
                else:
                    preferred_model = False

                # get the user's preferred image attachment setting
                if result is not None and result[4] is not None:
                    allow_images = bool(result[4])
                else:
                    allow_images = True

                # if the message is a reply to the bot we want to use the previous message as context
                if message.reference and message.reference.resolved.author == bot.user:
                    prompt_context = message.reference.resolved.content

                # prevent huge api calls
                if len(prompt) > 800:
                    await message.channel.send(content="Whoa, that's a lot of text, I can't be bothered to read that.")
                    return

                # print(prompt)
                # generate the response
                processed_response, image_prompts = await generate_response(prompt, prompt_context, message_setting, message.author.id, message.author.name, selected_sentiment, not privileged_origin, preferred_model, allow_images)
                if image_prompts:
                    file_locations = await image_factory(image_prompts, message.id)
                    discord_attachments = [discord.File(img_location) for img_location in file_locations if img_location is not None]

                async for msg in message.channel.history(limit=1):
                    split_response = split_message(processed_response)
                    if msg.id != message.id:
                        for i, response in enumerate(split_response):
                            if i == 0:
                                if image_prompts and discord_attachments and len(split_response) == 1:
                                    await message.channel.send(content=split_response[0], reference=message, files=discord_attachments[:10])
                                else:
                                    await message.channel.send(content=split_response[0], reference=message)
                            else:
                                if image_prompts and discord_attachments and i == len(split_response) - 1:
                                    await message.channel.send(content=response, files=discord_attachments[:10])
                                else:
                                    await message.channel.send(content=response)
                    else:
                        for i, response in enumerate(split_response):
                            if i == 0:
                                if image_prompts and discord_attachments and len(split_response) == 1:
                                    await message.channel.send(content=split_response[0], files=discord_attachments[:10])
                                else:
                                    await message.channel.send(content=split_response[0])
                            else:
                                if image_prompts and discord_attachments and i == len(split_response) - 1:
                                    await message.channel.send(content=response, files=discord_attachments[:10])
                                else:
                                    await message.channel.send(content=response)

                if image_prompts and discord_attachments and len(discord_attachments) > 10:
                    for i in range(10, len(discord_attachments), 10):
                        await message.channel.send(files=discord_attachments[i:i+10])

                if image_prompts and file_locations and None in file_locations:
                    await message.channel.send(content=f"**Note:** At least one image could not be generated, sorry about that.")

                clear_image_cache(message.id, len(image_prompts))
            else:
                await message.channel.send(content=f"**{message.author.name}**, you have run out of tokens for today. Please try again in **{int((result[1] - time.time()) / 3600)}h {int(((result[1] - time.time()) % 3600) / 60)}min**.")

if __name__ == "__main__":
    init_db()
    bot.run("<your_discord_bot_token>")
