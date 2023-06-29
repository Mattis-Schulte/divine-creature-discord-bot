import os
import asyncio
import aiofiles
import discord
import logging
import pyfirefly
from pyfirefly.utils import ImageOptions


class ImageGenerator:
    FIREFLY_BEARER_TOKEN: str = os.getenv("FIREFLY_BEARER_TOKEN")
    IMAGE_CACHE_LOCATION: str = "image_cache/"
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    def __init__(self, aspect_ratio: str):
        self.aspect_ratio = aspect_ratio
        self.firefly_session = None
        self.img = None

    async def __aenter__(self):
        """Create a new Adobe Firefly session."""
        self.firefly_session = await pyfirefly.Firefly(self.FIREFLY_BEARER_TOKEN)
        self.img = ImageOptions(image_styles=self.firefly_session.image_styles)
        self.img.set_aspect_ratio(self.aspect_ratio)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def generate_images(self, generation_id: int, image_descriptions: list[str]) -> list[discord.File | None]:
        """Generate images using Adobe Firefly."""
        tasks = [asyncio.create_task(self.generate_image(image_descriptions[i], self.img.options, generation_id, i)) for i in range(len(image_descriptions))]
        return await asyncio.gather(*tasks)

    async def generate_image(self, prompt: str, img_options: dict, generation_id: int, suffix: int) -> discord.File | None:
        """Generate an image using Adobe Firefly."""
        try:
            result = await self.firefly_session.text_to_image(prompt, **img_options)
            async with aiofiles.open(os.path.join(self.IMAGE_CACHE_LOCATION, f"{generation_id}_{suffix}.{result.ext}"), mode="wb+") as f:
                await f.write(result.image)
                logging.info(f"Successfully generated image {generation_id}_{suffix}")
                return discord.File(os.path.join(self.IMAGE_CACHE_LOCATION, f"{generation_id}_{suffix}.{result.ext}"))
        except (pyfirefly.exceptions.ImageGenerationDenied, pyfirefly.exceptions.Unauthorized, pyfirefly.exceptions.SessionExpired):
            logging.error(f"An error occurred while generating image {generation_id}_{suffix}")
            return None


def clear_image_cache(generation_id: int, number_of_images: int):
    """Clear the image cache."""
    for i in range(number_of_images):
        try:
            os.remove(os.path.join(ImageGenerator.IMAGE_CACHE_LOCATION, f"{generation_id}_{i}.jpeg"))
        except FileNotFoundError:
            pass
        