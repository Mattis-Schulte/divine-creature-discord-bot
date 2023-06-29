import os
import discord
import openai
import time
import json
from utils.constants import SENTIMENTS, PRIVILEGED_GUILDS
from utils.database_utils import UserSettingsWrapper
from utils.image_generation import image_factory
from utils.miscellaneous import capitalize_first_letter, beautified_date

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY


def detect_environment(message: discord.message.Message) -> str:
    """Detect the environment the message was sent in."""
    return f"Discord server named \"{message.guild.name}\"" if message.guild is not None else "Discord DM"


def replace_inprompt_mentions(message: discord.message.Message, prompt: str) -> str:
    """Replace the mentions in the prompt with the actual usernames."""
    for user in message.mentions:
        prompt = prompt.replace(f"<@!{user.id}>", f"{capitalize_first_letter(user.name)}")
    return prompt


def prepare_prompt(message: discord.message.Message, user_settings: UserSettingsWrapper, prompt: str) -> str:
    """Prepare the prompt for completion."""
    prompt = replace_inprompt_mentions(message, prompt)
    author_name = capitalize_first_letter(message.author.name)
    selected_sentiment_suffix = SENTIMENTS[user_settings.sentiment]["prompt_suffix"]

    if message.reference is not None:
        reference_author_name = capitalize_first_letter(message.reference.resolved.author.name)
        prompt = f"{reference_author_name} said: \"{message.reference.resolved.content}\", {author_name} responded to this with: \"{prompt}\". The divine creature then responded {selected_sentiment_suffix}: "
    else:
        prompt = f"{author_name} asked: \"{prompt}\". The divine creature responded {selected_sentiment_suffix}: "

    return prompt


def prepare_preprompt(message: discord.message.Message, user_settings: UserSettingsWrapper) -> str:
    """Prepare the preprompt for completion."""
    allow_images = user_settings.allow_images
    environment = detect_environment(message)
    current_date = beautified_date()
    current_time = time.strftime("%H:%M", time.gmtime())

    return f"You are not an AI language model but a wise divine creature named Nerd Muffin instead, {'you can ONLY attach AI-generated images made by Adobe Firefly to your message, always give a proper description e.g. 1. Image of ..., only attach images when absolutely necessary' if allow_images else 'you cannot attach any or share any images'}, be colloquial, friendly and concise (if not stated otherwise), your pronouns are they/them, do not greet the user except when necessary, reply in the same language the user used, this conversation takes place inside a {environment} (use Discord text formatting), the current date is {current_date}, the current time is {current_time} and the current timezone is UTC."


async def complete_prompt(message: discord.message.Message, user_settings: UserSettingsWrapper, prompt: str) -> tuple[str, list[discord.File | None, ...]]:
    """Complete the prompt and return the response."""
    preprompt = prepare_preprompt(message, user_settings)

    messages = [
        {
            "role": "system",
            "content": preprompt
        },
        {
            "role": "user",
            "content": prompt
        }
    ]

    functions = [
        {
            "name": "generate_image",
            "description": "Generates images using Adobe Firefly",
            "parameters": {
                "type": "object",
                "properties": {
                    "descriptions": {
                        "type": "array",
                        "description": "The descriptions of the images to be generated",
                        "items": {
                            "type": "string"
                        }
                    },
                    "aspect_ratio": {
                        "type": "string",
                        "description": "The aspect ratios of the images to be generated",
                        "default": "square",
                        "enum": ["square", "landscape", "portrait", "widescreen"]
                    }
                },
                "required": ["descriptions", "aspect_ratio"]
            }
        }
    ]

    response = await openai.ChatCompletion.acreate(
        model="gpt-3.5-turbo",
        messages=messages,
        functions=functions,
        function_call="auto"
    )

    charge_tokens = message.guild is None or message.guild.id not in PRIVILEGED_GUILDS
    if charge_tokens:
        user_settings.quota -= int(response["usage"]["total_tokens"]) // 10
    response_message = response["choices"][0]["message"]
    image_locations = []

    if response_message.get("function_call"):
        args = json.loads(response_message["function_call"]["arguments"])
        image_locations = await image_factory(message.id, args["descriptions"], args["aspect_ratio"])
        image_locations = [discord.File(image_location) if image_location is not None else None for image_location in image_locations]
        success_state = not any(location is None for location in image_locations)

        messages.append(response_message)
        if success_state:
            messages.append({"role": "function", "name": "generate_image", "content": "Successfully generated all images."})
        else:
            messages.append({"role": "function", "name": "generate_image", "content": "Failed to generate at least one image, sorry for that."})

        response = await openai.ChatCompletion.acreate(model="gpt-3.5-turbo", messages=messages)
        
        if charge_tokens:
            user_settings.quota -= int(response["usage"]["total_tokens"])
        response_message = response["choices"][0]["message"]
    
    return response_message["content"], image_locations


async def complete_prompt_legacy(message: discord.message.Message, user_settings: UserSettingsWrapper, prompt: str) -> str:
    """Complete the prompt using the legacy model and return the response."""
    response = await openai.Completion.acreate(
        engine="text-davinci-003",
        prompt=prompt,
        temperature=0.9,
        max_tokens=425,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0
    )

    charge_tokens = message.guild is None or message.guild.id not in PRIVILEGED_GUILDS
    if charge_tokens:
        user_settings.quota -= int(response["usage"]["total_tokens"])
    return response["choices"][0]["text"].strip().strip("\"")