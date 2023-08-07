from dataclasses import asdict
import json
import logging
import time
import pytz

from retrying import retry
from typing import Literal, Union

from soundfleet_player import client
from soundfleet_player import cache
from soundfleet_player.conf import settings
from soundfleet_player.types import (
    AdBlock,
    AudioTrack,
    DeviceState,
    MusicBlock,
)
from soundfleet_player.utils import (
    get_local_time_from_time_str,
    get_redis_conn,
    Null,
)


logger = logging.getLogger(__name__)


class SyncFailed(Exception):
    pass


class Device:
    SYNC_RETRY_COUNT = 10
    SYNC_COUNTDOWN_TIME = 10

    def __init__(self):
        self._redis = get_redis_conn()
        self._cache = cache.DeviceCache()
        self._music_blocks_cache = cache.MusicBlocksCache()
        self._ad_blocks_cache = cache.AdBlocksCache()
        self._audio_tracks_cache = cache.AudioTracksCache()
        self._sync_in_progress = False

    def sync(self):
        if self._sync_in_progress:
            return
        try:
            state = self.get_state()
            self._cache.set(state["device"])
            self._music_blocks_cache.set(state["music_blocks"])
            self._ad_blocks_cache.set(state["ad_blocks"])
            self._audio_tracks_cache.update(state["audio_tracks"])
        except SyncFailed:
            logger.error("Failed to sync device, using state from cache.")
        finally:
            self._ack_sync()

    def get_state(self) -> DeviceState:
        sync_id = self._start_sync_task()
        return self._get_device_state(sync_id)

    def update_device_state_cache(self, **kwargs) -> None:
        device = self._cache.get()
        device.update(**kwargs)
        self._cache.set(device)

    def update_music_blocks_cache(self, music_blocks) -> None:
        self._music_blocks_cache.set(music_blocks)

    @property
    def volume(self) -> int:
        device = self._cache.get() or {}
        return device.get("volume", 100)

    @property
    def timezone(self) -> pytz.timezone:
        device = self._cache.get() or {}
        tzname = device.get("timezone_name", "UTC")
        return pytz.timezone(tzname)

    @property
    def playback_priority(self) -> Literal["music", "ads"]:
        device = self._cache.get() or {}
        return device.get("playback_priority", "music")

    @property
    def music_blocks(self) -> MusicBlock:
        music_blocks = self._music_blocks_cache.get() or []
        music_blocks = map(
            lambda block: MusicBlock(
                {
                    "id": block["id"],
                    "start": get_local_time_from_time_str(
                        self.timezone, block["start"]
                    ),
                    "end": get_local_time_from_time_str(
                        self.timezone, block["end"]
                    ),
                    "tracks": block["tracks"],
                }
            ),
            music_blocks,
        )
        return list(music_blocks)

    @property
    def ad_blocks(self) -> list[AdBlock]:
        ad_blocks = self._ad_blocks_cache.get() or []
        ad_blocks = map(
            lambda block: AdBlock(
                {
                    "id": block["id"],
                    "start": get_local_time_from_time_str(
                        self.timezone, block["start"]
                    ),
                    "end": get_local_time_from_time_str(
                        self.timezone, block["end"]
                    ),
                    "ads_count_per_block": block["ads_count_per_block"],
                    "play_all_ads": block["play_all_ads"],
                    "playback_interval": block["playback_interval"],
                    "tracks": block["tracks"],
                }
            ),
            ad_blocks,
        )
        return list(ad_blocks)

    @property
    def audio_tracks(self) -> list[AudioTrack]:
        return self._audio_tracks_cache.all()

    def get_audio_track(self, track_id: int):
        return self._audio_tracks_cache.get(track_id)

    @property
    def _state_url(self) -> str:
        return "{}/api/devices/{}/get-state/".format(
            settings.APP_URL, settings.DEVICE_ID
        )

    @retry(
        stop_max_attempt_number=3, wait_random_min=10000, wait_random_max=30000
    )
    def _start_sync_task(self) -> str:
        """
        Request device state.
        :return: async result uuid
        """
        self._sync_in_progress = True
        response = client.make_request(self._state_url, "get")
        if not response:
            self._sync_in_progress = False
            raise SyncFailed("Failed to start sync task on remote server")

        if response.status_code == 200:
            return response.json().get("task_id")
        else:
            raise SyncFailed()

    def _get_device_state(self, sync_id: str) -> Union[DeviceState, None]:
        response_data = Null()
        retry_count = self.SYNC_RETRY_COUNT
        countdown_time = self.SYNC_COUNTDOWN_TIME

        while not response_data.get("result"):
            if retry_count <= 0:
                break
            response = client.make_request(
                self._state_url,
                "get",
                params={"task_id": sync_id},
                response_timeout=60,
            )
            response_data = response.json()

            if "result" in response_data:
                # task is processed at this point and returns result
                logger.info("Successfully synced device state.")
                self._sync_in_progress = False
                return DeviceState(response_data["result"])

            logger.debug(
                f"Task is still executing. Retrying in {countdown_time} seconds..."
            )
            time.sleep(countdown_time)
            countdown_time = min(countdown_time * 2, 180)

            retry_count -= 1
        self._sync_in_progress = False
        raise SyncFailed()

    def _ack_sync(self) -> None:
        signal = json.dumps(("DEVICE_SYNC", []))
        while not self._redis.publish(settings.SCHEDULER_REDIS_CHANNEL, signal):
            time.sleep(0.1)
