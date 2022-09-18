import redis


def is_redis_running(**kwargs):
    try:
        r = redis.Redis(**kwargs)
        r.ping()
        return True
    except redis.exceptions.ConnectionError:
        return False
    except Exception:
        raise


class ExitAfter:
    def __init__(self, log_count):
        self.loops = iter(range(log_count))

    def __call__(self, *args, **kwargs):
        step = next(self.loops, None)
        return step is not None
