import os
import asyncio
import discord
import io
import logging
import pyfirefly
from pyfirefly.utils import ImageOptions


class ImageGenerator:
    """
    Image generation handler for Adobe Firefly.

    :param aspect_ratio: The aspect ratio of the generated images.
    """
    FIREFLY_BEARER_TOKEN = os.getenv("FIREFLY_BEARER_TOKEN")
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    def __init__(self, aspect_ratio: str):
        self.firefly_session = None
        self.img = None
        self.aspect_ratio = aspect_ratio

    async def __aenter__(self):
        """
        Create a new Adobe Firefly session.
        """
        try:
            self.firefly_session = await pyfirefly.Firefly(self.FIREFLY_BEARER_TOKEN)
            self.img = ImageOptions(image_styles=self.firefly_session.image_styles)
            self.img.set_aspect_ratio(self.aspect_ratio)
        except pyfirefly.exceptions.Unauthorized:
            logging.error("An error occurred while creating a new Adobe Firefly session. Check your bearer token.")
            self.firefly_session = None
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def generate_images(self, generation_id: int, image_descriptions: list[str]) -> list[discord.File | None]:
        """
        Generate mutliple images with Adobe Firefly and return them as Discord files.
        
        :param generation_id: The ID of the generation.
        :param image_descriptions: The descriptions to generate images from.

        :return: A list of generated images as Discord files.
        """
        tasks = [asyncio.create_task(self.generate_image(description, self.img, f"{generation_id}_{i}")) for i, description in enumerate(image_descriptions)]
        return await asyncio.gather(*tasks)

    async def generate_image(self, prompt: str, img_options: dict, filename) -> discord.File | None:
        """
        Generate an image with Adobe Firefly and return it as a Discord file.
        
        :param prompt: The prompt to generate an image from.
        :param img_options: The image options to use.
        :param filename: The filename of the image.

        :return: The generated image as a Discord file.
        """
        if self.firefly_session is None:
            logging.error(f"Cannot generate image {filename}. No Adobe Firefly session.")
            return None

        try:
            result = await self.firefly_session.text_to_image(prompt, **img_options.options)
            logging.info(f"Successfully generated image {filename}")
            return discord.File(io.BytesIO(result.image), filename=f"{filename}.{result.ext}", description=prompt)
        except (pyfirefly.exceptions.ImageGenerationDenied, pyfirefly.exceptions.Unauthorized, pyfirefly.exceptions.SessionExpired) as e:
            logging.error(f"An error occurred while generating image {filename}: {e}")
            return None
