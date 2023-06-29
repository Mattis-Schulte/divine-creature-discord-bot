import os
import asyncio
import aiofiles
import pyfirefly
from pyfirefly.utils import ImageOptions

FIREFLY_BEARER_TOKEN = os.getenv("FIREFLY_BEARER_TOKEN")
IMAGE_CACHE_LOCATION = "image_cache/"


async def image_factory(generation_id: int, image_descriptions: list, aspect_ratio: str) -> list[str, ...]:
    firefly_session = await pyfirefly.Firefly(FIREFLY_BEARER_TOKEN)
    img = ImageOptions(image_styles=firefly_session.image_styles)
    img.set_aspect_ratio(aspect_ratio)
    tasks = [generate_image(firefly_session, image_descriptions[i], img.options, generation_id, i) for i in range(len(image_descriptions))]
    return await asyncio.gather(*tasks)


async def generate_image(firefly_session: pyfirefly.Firefly, prompt: str, img_options: dict, generation_id: int, suffix: int) -> str:
    result = await firefly_session.text_to_image(prompt, **img_options)
    async with aiofiles.open(f"{IMAGE_CACHE_LOCATION}{generation_id}_{suffix}.{result.ext}", mode="wb+") as f:
        await f.write(result.image)
        return f"{IMAGE_CACHE_LOCATION}{generation_id}_{suffix}.{result.ext}"


def clear_image_cache(generation_id: int, number_of_images: int):
    for i in range(number_of_images):
        try:
            os.remove(f"{IMAGE_CACHE_LOCATION}{generation_id}_{i}.jpeg")
        except FileNotFoundError:
            pass