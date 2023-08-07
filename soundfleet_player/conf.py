import environ


class ImproperlyConfigured(Exception):
    pass


class Settings(dict):
    def __getattr__(self, item):
        return self.get(item)

    def __setattr__(self, key, value):
        self[key] = value


def setup_settings():
    env = environ.Env()
    env.read_env(env_file="/etc/soundfleet.env")
    DEBUG = env("DEBUG", default=0)
    try:
        return Settings(
            DEBUG=DEBUG,
            DEVICE_ID=env("DEVICE_ID"),
            APP_URL=env("APP_URL"),
            API_KEY=env("API_KEY"),
            DOWNLOAD_DIR=env("DOWNLOAD_DIR"),
            MEDIA_BACKEND=env(
                "MEDIA_BACKEND",
                default="soundfleet_player.media_backends.vlc",
            ),
            SCHEDULER_REDIS_CHANNEL=env(
                "SCHEDULER_REDIS_CHANNEL",
                default="SCHEDULER_REDIS_CHANNEL",
            ),
            PLAYER_REDIS_CHANNEL=env(
                "PLAYER_REDIS_CHANNEL", default="PLAYER_REDIS_CHANNEL"
            ),
            LOGGING_CONFIG={
                "version": 1,
                "disable_existing_loggers": True,
                "formatters": {
                    "standard": {
                        "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
                    },
                },
                "handlers": {
                    "default": {
                        "level": "DEBUG" if DEBUG else "INFO",
                        "formatter": "standard",
                        "class": "logging.StreamHandler"
                    },
                    # logstash: TODO
                },
                "loggers": {
                    "": {
                        "handlers": ["default"],
                        "level": "DEBUG" if DEBUG else "INFO",
                    }
                }
            },
        )
    except KeyError as e:
        raise ImproperlyConfigured("Set {} environment variable.".format(e))


settings = setup_settings()
