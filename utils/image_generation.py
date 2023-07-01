import os
import asyncio
import discord
import io
import logging
import pyfirefly
from pyfirefly.utils import ImageOptions


class ImageGenerator:
    FIREFLY_BEARER_TOKEN = os.getenv("FIREFLY_BEARER_TOKEN")
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    def __init__(self, aspect_ratio: str):
        self.firefly_session = None
        self.img = None
        self.aspect_ratio = aspect_ratio

    async def __aenter__(self):
        """Create a new Adobe Firefly session."""
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
        """Generate mutliple images with Adobe Firefly and return them as Discord files."""
        tasks = [asyncio.create_task(self.generate_image(image_descriptions[i], self.img, generation_id, i)) for i in range(len(image_descriptions))]
        return await asyncio.gather(*tasks)

    async def generate_image(self, prompt: str, img_options: dict, generation_id: int, suffix: int) -> discord.File | None:
        """Generate an image with Adobe Firefly and return it as a Discord file."""
        image_name = f"{generation_id}_{suffix}"
        if self.firefly_session is None:
            logging.error(f"Cannot generate image {image_name}. No Adobe Firefly session.")
            return None

        try:
            pyfirefly.Result
            result = await self.firefly_session.text_to_image(prompt, **img_options.options)
            logging.info(f"Successfully generated image {image_name}")
            return discord.File(io.BytesIO(result.image), filename=f"{image_name}.{result.ext}", description=prompt)
        except (pyfirefly.exceptions.ImageGenerationDenied, pyfirefly.exceptions.Unauthorized, pyfirefly.exceptions.SessionExpired) as e:
            logging.error(f"An error occurred while generating image {image_name}: {e}")
            return None
