import logging
import redis
from app.core.config import settings

logger = logging.getLogger("redis_client")

class RedisClientWrapper:
    def __init__(self, url):
        self.client = redis.Redis.from_url(url, decode_responses=True)

    def get(self, key):
        try:
            return self.client.get(key)
        except Exception:
            logger.exception(f"Redis get failed for key {key}")
            raise

    def set(self, key, value, *args, **kwargs):
        try:
            return self.client.set(key, value, *args, **kwargs)
        except Exception:
            logger.exception(f"Redis set failed for key {key}")
            raise

    def exists(self, key):
        try:
            return self.client.exists(key)
        except Exception:
            logger.exception(f"Redis exists failed for key {key}")
            raise

    def incrby(self, key, amount=1):
        try:
            return self.client.incrby(key, amount)
        except Exception:
            logger.exception(f"Redis incrby failed for key {key}")
            raise

    def incrbyfloat(self, key, amount=1.0):
        try:
            return self.client.incrbyfloat(key, amount)
        except Exception:
            logger.exception(f"Redis incrbyfloat failed for key {key}")
            raise

    def publish(self, channel, message):
        try:
            return self.client.publish(channel, message)
        except Exception:
            logger.exception(f"Redis publish failed for channel {channel}")
            raise

    def pubsub(self, *args, **kwargs):
        try:
            return self.client.pubsub(*args, **kwargs)
        except Exception:
            logger.exception("Redis pubsub failed")
            raise

    def delete(self, key):
        try:
            return self.client.delete(key)
        except Exception:
            logger.exception(f"Redis delete failed for key {key}")
            raise

    def ping(self):
        try:
            return self.client.ping()
        except Exception:
            logger.exception("Redis ping failed")
            raise

    def pipeline(self):
        try:
            return self.client.pipeline()
        except Exception:
            logger.exception("Redis pipeline failed")
            raise

redis_client = RedisClientWrapper(settings.REDIS_URL)
