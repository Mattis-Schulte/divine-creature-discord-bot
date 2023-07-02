import os
import redis
import hashlib
import time
from dotenv import load_dotenv
from typing import NamedTuple
from utils.constants import DEFAULT_SENTIMENT, DEFAULT_QUOTA
from utils.miscellaneous import calc_refresh_time

load_dotenv()
REDIS_PWD = os.getenv("REDIS_PWD")
SALTING_VALUE = os.getenv("SALTING_VALUE")
r = redis.Redis(host="0.0.0.0", port=8080, db=0, password=REDIS_PWD)


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

    def __init__(self, user_id):
        self.user_id = user_id
        self.user_hash = self.hash_user_id(user_id)
        self.settings = self.get_user_settings()

    @staticmethod
    def hash_user_id(user_id: int) -> str:
        """
        Hash the user ID using Blake2b.
        
        :param user_id: The user's ID.

        :return: The hashed user ID.
        """
        return hashlib.blake2b((SALTING_VALUE + str(user_id)).encode(), digest_size=16).hexdigest()
    
    def get_user_settings(self) -> UserSettings:
        """
        Get the user settings from Redis database.
        
        :return: The user settings.
        """
        user_settings = r.hgetall(f"user_settings:{self.user_hash}")
        if not user_settings:
            user_settings = self.default_user_settings()
            self.set_user_settings(user_settings)
        else:
            user_settings = self.parse_user_settings(user_settings)

        if user_settings.refresh_time < int(time.mktime(time.gmtime())):
            user_settings = user_settings._replace(refresh_time=calc_refresh_time(), quota=DEFAULT_QUOTA)
            self.set_user_settings({"refresh_time": user_settings.refresh_time, "quota": user_settings.quota})

        return user_settings

    @staticmethod
    def default_user_settings() -> UserSettings:
        """
        Return the default user settings as a UserSettings numedtuple.
        
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
        Parse user settings from Redis hash to a UserSettings namedtuple.
        
        :param settings: The user settings from Redis database.
        
        :return: The parsed user settings.
        """
        parsed_settings = {
            key.decode(): UserSettings.__annotations__.get(key.decode(), str)(value.decode()) 
            if key.decode() in UserSettings.__annotations__ else None for key, value in settings.items()
        }
        return UserSettings(**parsed_settings)

    def set_user_settings(self, settings: UserSettings | dict):
        """
        Save user settings to Redis database.
        
        :param settings: The user settings to save, either as a UserSettings namedtuple or a dict.
        """
        if isinstance(settings, UserSettings):
            settings = settings._asdict()
        
        with r.pipeline() as pipe:
            for key, value in settings.items():
                r.hset(f"user_settings:{self.user_hash}", key, value)
            pipe.execute()

    def __getattr__(self, item: str) -> str | int:
        """
        Get a attribute from the UserSettings namedtuple or the object itself.
        
        :param item: The attribute to get.

        :return: The attribute.
        """
        if item in UserSettings._fields:
            return getattr(self.settings, item)
        else:
            return super().__getattribute__(item)

    def __setattr__(self, name: str, value: str | int):
        """
        Set an attribute in the UserSettings namedtuple and call set_user_settings() or set the attribute in the object itself.
        
        :param name: The attribute to set.
        :param value: The value to set the attribute to.
        """
        if name in UserSettings._fields:
            self.settings = self.settings._replace(**{name: value})
            self.set_user_settings({name: value})
        else:
            super().__setattr__(name, value)
