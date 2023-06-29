import os
import redis
import hashlib
from time import time
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


class UserSettingsWrapper:
    def __init__(self, user_id):
        self.user_id = user_id
        self.user_hash = self.hash_user_id(user_id)
        self.settings = self.get_user_settings()

    @staticmethod
    def hash_user_id(user_id: int) -> str:
        """Hash the user ID using Blake2b."""
        return hashlib.blake2b((SALTING_VALUE + str(user_id)).encode(), digest_size=16).hexdigest()
    
    def get_user_settings(self) -> UserSettings:
        """Get the user settings from Redis database."""
        user_settings = r.hgetall(f"user_settings:{self.user_hash}")
        if not user_settings:
            user_settings = self.default_user_settings()
            self.set_user_settings(user_settings)
        else:
            user_settings = self.parse_user_settings(user_settings)

        if user_settings.refresh_time < int(time()):
            user_settings = user_settings._replace(refresh_time=calc_refresh_time(), quota=DEFAULT_QUOTA)
            self.set_user_settings({"refresh_time": user_settings.refresh_time, "quota": user_settings.quota})

        return user_settings

    @staticmethod
    def default_user_settings() -> UserSettings:
        """Return the default user settings."""
        return UserSettings(
            quota=DEFAULT_QUOTA,
            refresh_time=calc_refresh_time(),
            sentiment=DEFAULT_SENTIMENT,
            use_legacy=int(False),
            allow_images=int(True)
        )

    @staticmethod
    def parse_user_settings(settings: dict) -> UserSettings:
        """Parse user settings from Redis hash to UserSettings namedtuple."""
        parsed_settings = {
            key.decode(): UserSettings.__annotations__.get(key.decode(), str)(value.decode()) 
            if key.decode() in UserSettings.__annotations__ else None for key, value in settings.items()
        }
        return UserSettings(**parsed_settings)

    def set_user_settings(self, settings: UserSettings | dict):
        """Save user settings to Redis database."""
        if isinstance(settings, UserSettings):
            settings = settings._asdict()
        
        for key, value in settings.items():
            r.hset(f"user_settings:{self.user_hash}", key, value)

    def __getattr__(self, item: str) -> str | int:
        """Get attribute from UserSettings namedtuple."""
        if item in UserSettings._fields:
            return getattr(self.settings, item)
        else:
            return super().__getattribute__(item)

    def __setattr__(self, name: str, value: str | int):
        """Set attribute in UserSettings namedtuple and update Redis."""
        if name in UserSettings._fields:
            self.settings = self.settings._replace(**{name: value})
            self.set_user_settings({name: value})
        else:
            super().__setattr__(name, value)
