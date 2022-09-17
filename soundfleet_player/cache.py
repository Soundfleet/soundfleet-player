import datetime
import json
import os

from soundfleet_player.storage import AudioTrackStorage
from soundfleet_player.utils import get_redis_conn


class RedisCache:

    _redis = None

    def __init__(self):
        self._redis = get_redis_conn()


class DeviceCache(RedisCache):
    def get_key(self):
        return "DEVICE"

    def get(self):
        val = self._redis.get(self.get_key())
        return json.loads(val) if val else {}

    def set(self, val):
        key = self.get_key()
        self._redis.set(key, json.dumps(val))


class MusicBlocksCache(RedisCache):
    def get_key(self):
        return "MUSIC_BLOCKS"

    def get(self):
        val = self._redis.get(self.get_key())
        return json.loads(val) if val else []

    def set(self, val):
        key = self.get_key()
        self._redis.set(key, json.dumps(val))


class AdBlocksCache(RedisCache):
    def get_key(self):
        return "AD_BLOCKS"

    def get(self):
        val = self._redis.get(self.get_key())
        return json.loads(val) if val else []

    def set(self, val):
        key = self.get_key()
        self._redis.set(key, json.dumps(val))


class AudioTracksCache(RedisCache):
    def get_key(self, id="*"):
        return "AUDIO_TRACK:{}".format(id)

    def set(self, track):
        id = track["id"]
        key = self.get_key(id)
        self._redis.set(key, json.dumps(track))

    def get(self, id):
        return json.loads(self._redis.get(self.get_key(id)))

    def all(self):
        key = self.get_key()
        return {
            track["id"]: track
            for track in map(
                json.loads, [self._redis.get(k) for k in self._redis.keys(key)]
            )
        }

    def update(self, track_list):
        key = self.get_key()
        current_keys = set(self._redis.keys(key))
        new_keys = set([self.get_key(track["id"]) for track in track_list])
        to_delete = current_keys - new_keys
        tracks_to_delete = [json.loads(self._redis.get(k)) for k in to_delete]
        if to_delete:
            self._redis.delete(*to_delete)
            AudioTrackStorage.remove_tracks(*tracks_to_delete)
        for track in track_list:
            self.set(track)


class DownloadLRUCache(RedisCache):
    def __init__(self, download_dir):
        super().__init__()

        init_t = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for fname in os.listdir(download_dir):
            key = self.get_key(fname)
            if self._redis.get(key):
                continue
            self._redis.set(self.get_key(fname), init_t)

    def get_key(self, filename="*"):
        return f"DL:{filename}"

    def touch(self, filename):
        key = self.get_key(filename)
        self._redis.set(
            key, datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    def remove(self, filename):
        key = self.get_key(filename)
        self._redis.delete(key)

    def all(self):
        key = self.get_key()
        return {
            k.split(":")[-1]: datetime.datetime.strptime(
                self._redis.get(k), "%Y-%m-%d %H:%M:%S"
            )
            for k in self._redis.keys(key)
        }
