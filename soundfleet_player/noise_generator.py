import datetime
import json
import logging
import os
import random

from collections import deque
from functools import partial

from soundfleet_player.conf import settings
from soundfleet_player.storage import AudioTrackStorage, DownloadFailed
from soundfleet_player.utils import get_redis_conn


logger = logging.getLogger(__name__)


class BaseGenerator:
    def __init__(self, device):
        self._storage = AudioTrackStorage()
        self._device = device
        self._redis = get_redis_conn()

    @staticmethod
    def _track_absolute_path(track):
        return os.path.join(settings.DOWNLOAD_DIR, track["file"])


class MusicBlockBasedGenerator(BaseGenerator):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._history = deque(maxlen=10)

    def draw_and_download(self, draw_time):
        def _block_cmp(t, block):
            return block["start"] <= t <= block["end"]

        cmp = partial(_block_cmp, draw_time)
        block = next(filter(cmp, self._device.music_blocks), None)

        population = block["tracks"] if block is not None else None

        if not population:
            self._notify_finished()
            return

        track_id = self._draw(population)
        if not track_id:
            self._notify_finished()
            return

        # save drawn track id in history to avoid frequent repetition
        self._history.append(track_id)
        track = self._device.get_audio_track(track_id)
        track.update(uri=f"file://{self._track_absolute_path(track)}")
        logger.debug("Drawn music track: {}".format(track))
        self._download_and_ack(track)
        self._notify_finished()

    def _draw(self, population):
        track_id = None
        # try to draw 100 times if drawn track id is in history of 10 tracks
        for _ in range(100):
            track_id = random.choice(population)
            if track_id not in self._history:
                break
        return track_id

    def _download_and_ack(self, track):
        try:
            track = self._storage.download(track)
            signal = json.dumps(
                (
                    "MUSIC_TRACK_DOWNLOADED",
                    [
                        track,
                    ],
                )
            )
            while not self._redis.publish(
                settings.SCHEDULER_REDIS_CHANNEL, signal
            ):
                continue
        except DownloadFailed:
            signal = json.dumps(
                (
                    "MUSIC_TRACK_DOWNLOAD_FAILED",
                    [
                        track,
                    ],
                )
            )
            while not self._redis.publish(
                settings.SCHEDULER_REDIS_CHANNEL, signal
            ):
                continue

    def _notify_finished(self):
        signal = json.dumps(("MUSIC_GENERATOR_FINISHED", []))
        while not self._redis.publish(settings.SCHEDULER_REDIS_CHANNEL, signal):
            continue


class AdBlockBasedGenerator(BaseGenerator):
    _current_block_id = None
    _next_block = None

    def draw_and_download(self, draw_time):
        def _block_cmp(t, block):
            return block["start"] <= t <= block["end"]

        cmp = partial(_block_cmp, draw_time)
        block = next(filter(cmp, self._device.ad_blocks), None)

        if block is None:
            self._notify_finished()
            return

        if block["id"] != self._current_block_id:
            self._current_block_id = block["id"]
            # block has changed, draw ads
            tracks, next_block_in = self._draw_ads(block)
            self._next_block = draw_time + next_block_in
        else:
            next_block = self._next_block or draw_time
            if draw_time >= next_block:
                tracks, next_block_in = self._draw_ads(block)
                self._next_block = draw_time + next_block_in
            else:
                tracks = []
        for track in tracks:
            logger.debug("Drawn ad track: {}".format(track))
            self._download_and_ack(track)
        self._notify_finished()

    def _notify_finished(self):
        signal = json.dumps(("ADS_GENERATOR_FINISHED", []))
        while not self._redis.publish(settings.SCHEDULER_REDIS_CHANNEL, signal):
            continue

    def _draw_ads(self, block):
        population = block["tracks"]
        if not population:
            logger.debug("No ad tracks to draw from, skipping...")
            return [], datetime.timedelta(minutes=block["playback_interval"])

        if block["play_all_ads"]:
            tracks = [
                self._device.get_audio_track(track_id)
                for track_id in block["tracks"]
            ]
        else:
            track_ids = random.choices(
                population, k=block["ads_count_per_block"]
            )
            tracks = [
                self._device.get_audio_track(track_id) for track_id in track_ids
            ]
        tracks = list(
            map(
                lambda track: dict(
                    track,
                    **{"uri": f"file://{self._track_absolute_path(track)}"},
                ),
                tracks,
            )
        )
        duration = sum(map(lambda track: track["length"], tracks)) - 1
        return (
            tracks,
            datetime.timedelta(
                seconds=max(
                    duration - 1, 0
                ),  # - 1 second is necessary when loop ads is enabled,
                # giving time to draw
                # ads again before music start playing
                minutes=block["playback_interval"],
            ),
        )

    def _download_and_ack(self, track):
        track = self._storage.download(track)
        signal = json.dumps(
            (
                "AD_TRACK_DOWNLOADED",
                [
                    track,
                ],
            )
        )
        while not self._redis.publish(settings.SCHEDULER_REDIS_CHANNEL, signal):
            continue
