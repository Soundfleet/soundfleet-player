import json
import logging
import time
import traceback

from soundfleet_player.conf import settings
from soundfleet_player.media_backends.base import MediaBackend
from soundfleet_player.utils import (
    Null,
    get_and_decode_redis_message,
    get_redis_conn,
)


logger = logging.getLogger(__name__)


class Player:
    _current_track = None

    def __init__(self, media_backend: MediaBackend):
        self._media_backend = media_backend
        self._redis = get_redis_conn()
        self._redis_pipe = self._redis.pubsub()
        self._redis_pipe.subscribe(settings.PLAYER_REDIS_CHANNEL)
        self._signal_map = {
            "PLAY": self._on_play,
            "SET_VOLUME": self._on_set_volume,
            "SKIP": self._on_skip,
        }

    def run(self):
        counter = 1
        self._ack_ready()
        while self._should_run():
            # check if any sound is playing and send signal to scheduler if not
            if self._current_track and not self._is_playing():
                logger.debug(
                    f"Player finished playing {self._current_track},"
                    f" sending TRACK_FINISHED signal"
                )
                self._ack_finish()

            signal = get_and_decode_redis_message(self._redis_pipe, logger)
            if signal:
                self._dispatch_signal(signal)
            if counter % 100 == 0:
                # ack scheduler that player is idle every 100th iteration
                # which is about 10s
                if not self._is_playing():
                    logger.debug("Player is idle, sending PLAYER_IDLE signal")
                    self._ack_idle()
                counter = 1
            else:
                counter += 1
            time.sleep(0.1)

    @classmethod
    def _should_run(cls):
        return True

    def _dispatch_signal(self, signal):
        name, args = signal
        func = self._signal_map.get(name, Null())
        try:
            func(*args)
        except Exception as e:
            logger.error(
                "Invalid func call {}: {} \n {}".format(
                    func, e, traceback.format_exc()
                )
            )

    def _play(self, track):
        if self._is_playing():
            self._media_backend.stop()
        self._media_backend.play(track)
        self._current_track = track
        self._ack_play()
        # give player some time to connect to stream or load and play file
        t = time.time()
        while not self._is_playing():
            if time.time() - t > 10:  # wait 10s
                break
            logger.warning(
                f"Player not yet playing, "
                f"time left: {t - time.time()}s, track: {track}"
            )
            time.sleep(1)
        if self._is_playing():
            logger.info(f"Player started playing {track}")
        else:
            logger.error(f"Unable to play {track}")

    def _skip(self):
        if self._current_track and self._is_playing():
            self._media_backend.stop()
            self._ack_finish()

    def _set_volume(self, val):
        self._media_backend.set_volume(val)

    def _ack_ready(self):
        signal = json.dumps(("PLAYER_READY", []))
        while not self._redis.publish(settings.SCHEDULER_REDIS_CHANNEL, signal):
            time.sleep(0.1)

    def _ack_idle(self):
        signal = json.dumps(("PLAYER_IDLE", []))
        while not self._redis.publish(settings.SCHEDULER_REDIS_CHANNEL, signal):
            time.sleep(0.1)

    def _ack_play(self):
        signal = json.dumps(
            (
                "TRACK_PLAY",
                [
                    self._current_track,
                ],
            )
        )
        while not self._redis.publish(settings.SCHEDULER_REDIS_CHANNEL, signal):
            time.sleep(0.1)

    def _ack_finish(self):
        signal = json.dumps(
            (
                "TRACK_FINISHED",
                [
                    self._current_track,
                ],
            )
        )
        while not self._redis.publish(settings.SCHEDULER_REDIS_CHANNEL, signal):
            time.sleep(0.1)
        self._current_track = None

    def _is_playing(self):
        return self._media_backend.is_playing()

    # local signals
    def _on_play(self, track):
        self._play(track)

    def _on_set_volume(self, val):
        self._set_volume(val)

    def _on_skip(self):
        self._skip()
