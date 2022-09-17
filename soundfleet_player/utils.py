import datetime
import json
import pytz
import redis
import time


class Null:
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return self

    def __getattr__(self, item):
        return self

    def __setattr__(self, key, value):
        return self

    def __delattr__(self, item):
        return self

    def __repr__(self):
        return "Null()"

    def __iter__(self):
        return iter(())

    def __bool__(self):
        return False

    def __getitem__(self, item):
        return self

    def __setitem__(self, key, value):
        return self


class RedisQueue:
    def __init__(self, redis, name, namespace="queue"):
        self.key = "{}:{}".format(namespace, name)
        self._redis = redis

    @property
    def size(self):
        return self._redis.llen(self.key)

    @property
    def is_empty(self):
        return self.size == 0

    def put(self, item):
        self._redis.rpush(self.key, item)

    def clear(self):
        while self._redis.lpop(self.key) is not None or self.size > 0:
            pass

    def get(self, block=True, timeout=None):
        if block:
            # item is pair (key, val) or None
            item = self._redis.blpop(self.key, timeout=timeout)
            item = item[1] if item else None
        else:
            # item is val or None
            item = self._redis.lpop(self.key)
        return item


def get_and_decode_redis_message(redis_pipe, logger):
    try:
        msg = redis_pipe.get_message()
    except redis.exceptions.ConnectionError:
        logger.error("Redis connection closed.")
        return
    if msg and msg["type"] == "message":
        try:
            return json.loads(msg["data"])
        except TypeError as e:
            logger.error(
                "Received invalid signal format that caused "
                "exception {}".format(e)
            )


def get_local_time(timezone):
    utc_now = datetime.datetime.utcnow().replace(tzinfo=pytz.utc)
    return utc_now.astimezone(timezone)


def get_local_time_from_time_str(timezone, time_str):
    dt = get_local_time(timezone)
    t = datetime.datetime.strptime(time_str, "%H:%M:%S").time()
    return datetime.datetime.combine(dt, t).replace(tzinfo=dt.tzinfo)


def get_redis_conn(host="redis", port=6379, timeout=60 * 60):
    conn = redis.StrictRedis(
        host=host,
        port=port,
        db=0,
        encoding="utf-8",
        decode_responses=True,
    )
    redis_ready = False
    time_expires = time.time() + timeout
    while not redis_ready and time_expires - time.time() > 0:
        try:
            redis_ready = conn.ping()
        except redis.exceptions.ConnectionError:
            time.sleep(1)
    return conn
