import os
import discord
import openai
import time
import json
from utils.constants import SENTIMENTS, PRIVILEGED_GUILDS
from utils.database_utils import UserSettingsHandler
from utils.image_generation import ImageGenerator
from utils.miscellaneous import capitalize_first_letter, beautified_date


class CompletionHandler:
    """
    Completion handler for OpenAI's API.

    :param user_settings: The user settings of the user who sent the message.
    """
    def __init__(self, user_settings: UserSettingsHandler):
        openai.api_key = os.getenv("OPENAI_API_KEY")
        self.user_settings = user_settings

    @staticmethod
    def detect_environment(message: discord.message.Message) -> str:
        """
        Detect the environment the message was sent in.

        :param message: The message to detect the environment of.

        :return: The environment the message was sent in.
        """
        return f"Discord server named \"{message.guild.name}\"" if message.guild is not None else "Discord DM"

    @staticmethod
    def replace_inprompt_mentions(message: discord.message.Message, prompt: str) -> str:
        """
        Replace the mentions in the prompt with the actual usernames.
        
        :param message: The message to get the mentions from.
        :param prompt: The prompt to replace the mentions in.

        :return: The prompt with the mentions replaced.
        """
        for user in message.mentions:
            prompt = prompt.replace(f"<@{user.id}>", f"{capitalize_first_letter(user.name)}")
        return prompt

    @staticmethod
    def charge_tokens(message: discord.message.Message) -> bool:
        """
        Check if the user will be charged tokens for the completion.
        
        :param message: The message to check the eligibility of.

        :return: Whether the user will be charged tokens for the completion.
        """
        return message.guild is None or message.guild.id not in PRIVILEGED_GUILDS

    def prepare_prompt(self, message: discord.message.Message, prompt: str) -> str:
        """
        Prepare the prompt for completion.
        
        :param message: The message to prepare the prompt for.
        :param prompt: The prompt to prepare.

        :return: The prepared prompt.
        """
        prompt = self.replace_inprompt_mentions(message, prompt)
        author_name = capitalize_first_letter(message.author.name)
        selected_sentiment_suffix = SENTIMENTS[self.user_settings.sentiment]["prompt_suffix"]

        if message.reference is not None:
            reference_author_name = capitalize_first_letter(message.reference.resolved.author.name)
            prompt = f"{reference_author_name} said: \"{message.reference.resolved.content}\", {author_name} responded to this with: \"{prompt}\". The divine creature then responded {selected_sentiment_suffix}: \""
        else:
            prompt = f"{author_name} asked: \"{prompt}\". The divine creature responded {selected_sentiment_suffix}: \""

        return prompt

    def prepare_preprompt(self, message: discord.message.Message) -> str:
        """
        Prepare the preprompt for completion.
        
        :param message: The message to prepare the preprompt for.

        :return: The prepared preprompt.
        """
        selected_sentiment_suffix = SENTIMENTS[self.user_settings.sentiment]["prompt_suffix"]
        environment = self.detect_environment(message)
        current_date = beautified_date()
        current_time = time.strftime("%H:%M", time.gmtime())

        return f"You are not an AI language model but a divine creature named Nerd Muffin instead, respond {selected_sentiment_suffix}, {'you can ONLY attach AI-generated images made by Adobe Firefly to your message, only attach images when absolutely necessary' if self.user_settings.allow_images else 'you cannot attach any or share any images'}, be a friend and not an assistant, also be concise, your pronouns are they/them, reply in the same language the user used, this conversation takes place inside a {environment} (use Discord text formatting), the current date is {current_date} and the current time is {current_time} in the UTC timezone."

    async def handle_image_gen_function_call(self, message: discord.message.Message, completion_messages: list[dict, ...], response_message: dict) -> tuple[str, list[discord.File | None, ...]]:
        """
        Image generation function call handler.
        
        :param message: The message to handle the function call for.
        :param completion_messages: The completion messages to append the response to.
        :param response_message: The response message to handle.

        :return: The response message and the image locations.
        """
        args = json.loads(response_message["function_call"]["arguments"])
        async with ImageGenerator(args["aspect_ratio"]) as image_generator:
            image_locations = await image_generator.generate_images(message.id, args["descriptions"])
        success_state = not any(location is None for location in image_locations)

        completion_messages.append(response_message)
        if success_state:
            completion_messages.append({"role": "function", "name": "generate_image", "content": "Successfully generated all images."})
        else:
            completion_messages.append({"role": "function", "name": "generate_image", "content": "Failed to generate at least one image, sorry for that."})

        response = await openai.ChatCompletion.acreate(model="gpt-3.5-turbo", messages=completion_messages)

        if self.charge_tokens(message):
            self.user_settings.quota -= int(response["usage"]["total_tokens"]) // 10

        response_message = response["choices"][0]["message"]

        return response_message, image_locations

    async def complete_prompt(self, message: discord.message.Message, prompt: str) -> tuple[str, list[discord.File | None, ...]]:
        """
        Complete the prompt and return the response.
        
        :param message: The message to complete the prompt for.
        :param prompt: The prompt to complete.

        :return: The response and the image locations.
        """
        preprompt = self.prepare_preprompt(message)
        prompt = self.prepare_prompt(message, prompt)
        image_locations = []

        for _ in range(5):
            try:
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

                completion_args = {"model": "gpt-3.5-turbo", "messages": messages}
                if self.user_settings.allow_images:
                    completion_args["functions"] = functions

                response = await openai.ChatCompletion.acreate(**completion_args)

                if self.charge_tokens(message):
                    self.user_settings.quota -= int(response["usage"]["total_tokens"]) // 10

                response_message = response["choices"][0]["message"]

                if response_message.get("function_call"):
                    response_message, image_locations = await self.handle_image_gen_function_call(message, messages, response_message)

                return response_message["content"].strip().strip("\""), image_locations

            except (openai.error.ServiceUnavailableError, openai.error.RateLimitError, openai.error.APIError):
                pass
        else:
            return "I'm currently experiencing connection difficulties", image_locations

    async def complete_prompt_legacy(self, message: discord.message.Message, prompt: str) -> str:
        """
        Complete the prompt using the legacy model and return the response.
        
        :param message: The message to complete the prompt for.
        :param prompt: The prompt to complete.

        :return: The response.
        """
        prompt = self.prepare_prompt(message, prompt)

        for _ in range(5):
            try:
                response = await openai.Completion.acreate(
                    engine="text-davinci-003",
                    prompt=prompt,
                    temperature=0.9,
                    max_tokens=425,
                    top_p=1,
                    frequency_penalty=0,
                    presence_penalty=0
                )

                self.user_settings.quota -= int(response["usage"]["total_tokens"])
                return response["choices"][0]["text"].strip().strip("\"")

            except (openai.error.ServiceUnavailableError, openai.error.RateLimitError, openai.error.APIError):
                pass
        else:
            return "I'm currently experiencing connection difficulties, please try again later."
