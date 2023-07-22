import asyncio
import os
import hashlib
import time
from dotenv import load_dotenv
from redis.asyncio import Redis as aioredis
from typing import NamedTuple, Self
from utils.constants import DEFAULT_SENTIMENT, DEFAULT_QUOTA
from utils.miscellaneous import calc_refresh_time

load_dotenv()
REDIS_PWD = os.getenv("REDIS_PWD")
SALTING_VALUE = os.getenv("SALTING_VALUE")


class RedisConnection:
    """
    Redis connection handler.

    :param db: The database to connect to.
    """
    def __init__(self, db: int = 0):
        self.db = db
        self.conn = None

    async def __aenter__(self):
        self.conn = await aioredis(host="0.0.0.0", port=8080, db=self.db, password=REDIS_PWD, decode_responses=True)
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        await self.conn.close()


class UserSettings(NamedTuple):
    quota: int
    refresh_time: int
    sentiment: str
    use_legacy: int
    allow_images: int


class UserSettingsHandler:
    """
    User settings handler for the Redis database.

    :param user_id: The user's ID.
    """
    def __init__(self, user_id: int):
        self.user_id = user_id
        self.user_hash = self.hash_user_id(user_id)
        self.settings = None

    @staticmethod
    def hash_user_id(user_id: int) -> str:
        """
        Hash the user ID using Blake2b.
        
        :param user_id: The user's ID.

        :return: The hashed user ID.
        """
        return hashlib.blake2b((SALTING_VALUE + str(user_id)).encode(), digest_size=16).hexdigest()

    async def get_user_settings(self) -> Self:
        """
        Get the user settings from Redis.
        
        :return: The instance object.
        """
        async with RedisConnection() as r:
            user_settings = await r.hgetall(f"user_settings:{self.user_hash}")

        if not user_settings:
            user_settings = self.default_user_settings()
            await self.set_user_settings(user_settings)
        else:
            user_settings = self.parse_user_settings(user_settings)

        if user_settings.refresh_time < int(time.mktime(time.gmtime())):
            user_settings = user_settings._replace(refresh_time=calc_refresh_time(), quota=DEFAULT_QUOTA)
            await self.set_user_settings({"refresh_time": user_settings.refresh_time, "quota": user_settings.quota})

        self.settings = user_settings

        return self

    @staticmethod
    def default_user_settings() -> UserSettings:
        """
        Return the default user settings as a UserSettings object.
        
        :return: The default user settings.
        """
        return UserSettings(
            quota=DEFAULT_QUOTA,
            refresh_time=calc_refresh_time(),
            sentiment=DEFAULT_SENTIMENT,
            use_legacy=int(False),
            allow_images=int(False)
        )

    @staticmethod
    def parse_user_settings(settings: dict) -> UserSettings:
        """
        Parse user settings from Redis hash to a UserSettings object.
        
        :param settings: The user settings from Redis.
        
        :return: The parsed user settings.
        """
        parsed_settings = {
            key: UserSettings.__annotations__.get(key, str)(value)
            for key, value in settings.items() if key in UserSettings.__annotations__
        }
        return UserSettings(**parsed_settings)

    async def set_user_settings(self, settings: UserSettings | dict):
        """
        Save user settings to Redis.
        
        :param settings: The user settings to save, either as a UserSettings object or a dict.
        """
        if isinstance(settings, UserSettings):
            settings = settings._asdict()

        async with RedisConnection() as r, r.pipeline(transaction=True) as pipe:
            for key, value in settings.items():
                await pipe.hset(f"user_settings:{self.user_hash}", key, value)
            await pipe.execute()

    def __getattr__(self, item: str) -> str | int:
        """
        Get an attribute from the UserSettings object or the parent class.
        
        :param item: The attribute to get.

        :return: The attribute.

        :raises AttributeError: If the user settings have not been loaded.
        """
        if item in UserSettings._fields:
            if self.settings is None:
                raise AttributeError("User settings not loaded.")
            
            return getattr(self.settings, item)
        else:
            return super().__getattribute__(item)

    def __setattr__(self, name: str, value: str | int):
        """
        Set an attribute in the UserSettings object or the parent class.
        
        :param name: The attribute to set.
        :param value: The value to set the attribute to.
        """
        if name in UserSettings._fields:
            self.settings = self.settings._replace(**{name: value})
            asyncio.create_task(self.set_user_settings({name: value}))
        else:
            super().__setattr__(name, value)
