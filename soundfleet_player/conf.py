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
    try:
        return Settings(
            DEBUG=env("DEBUG", default=0),
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
            PLAYER_LOG_FILE=env("PLAYER_LOG_FILE", default="/var/log/player.log")
        )
    except KeyError as e:
        raise ImproperlyConfigured("Set {} environment variable.".format(e))


settings = setup_settings()
