import datetime
import json
import logging
import threading
import time
import traceback

from soundfleet_player import client
from soundfleet_player.conf import settings
from soundfleet_player.noise_generator import (
    AdBlockBasedGenerator,
    MusicBlockBasedGenerator,
)
from soundfleet_player.device import Device
from soundfleet_player.utils import (
    get_and_decode_redis_message,
    get_local_time,
    get_redis_conn,
    Null,
)


logger = logging.getLogger(__name__)


class Scheduler:

    BUFFER_LENGTH = 10

    def __init__(self):
        self._device = Device()

        self._redis = get_redis_conn()

        self._redis_pipe = self._redis.pubsub()
        self._redis_pipe.subscribe(settings.SCHEDULER_REDIS_CHANNEL)

        self._player_ready = False
        self._player_idle = None
        self._music = []
        self._ads = []

        self._ads_generator = None
        self._ads_generator_busy = False
        self._music_generator = None
        self._music_generator_busy = False

        self._last_device_sync = None

        self._signal_map = {
            "PLAYER_READY": self._on_player_ready,
            "PLAYER_IDLE": self._on_player_idle,
            "TRACK_FINISHED": self._on_track_finished,
            "TRACK_PLAY": self._on_track_play,
            "DEVICE_SYNC": self._on_device_sync,
            "AD_TRACK_DOWNLOADED": self._on_ad_track_download,
            "MUSIC_TRACK_DOWNLOADED": self._on_music_track_download,
            "MUSIC_TRACK_DOWNLOAD_FAILED": self._on_music_track_download_failure,  # noqa: E501
            "ADS_GENERATOR_FINISHED": self._on_ads_generator_finish,
            "MUSIC_GENERATOR_FINISHED": self._on_music_generator_finish,
        }

        self._current_track = None
        self._next_track_draw_time = None

    def run(self):
        self._device.sync()
        counter = 1
        while self._should_run():
            signal = get_and_decode_redis_message(self._redis_pipe, logger)
            if signal:
                self._dispatch_signal(signal)

            if self._device.playback_priority == "ads_over_music":
                self._schedule_ads_over_music()
            else:
                self._schedule_music_over_ads()

            # generate noises
            # limit number of draws by spawning them every 1s instead of 0.1s
            if counter % 10 == 0:
                self._run_generator(self._generate_ads)
                self._run_generator(self._generate_music)

            # every 10m reset counter and sync device if day has changed
            if counter % 6000 == 0:
                counter = 1
                now = get_local_time(self._device.timezone)
                if now.day != self._last_device_sync.day:
                    self._device.sync()
            else:
                counter += 1

            time.sleep(0.1)

    def _schedule_ads_over_music(self):
        if self._player_ready:
            track = None
            if self._current_track is None:
                # player stopped playing, pick ad or music
                track = self._pick_next_track()
            elif self._current_track["track_type"] == "music" and self._ads:
                # if ads are generated then skip music and play ads
                track = self._pick_next_track()
            if track is not None:
                self._play_track(track)

    def _schedule_music_over_ads(self):
        if self._player_ready and self._current_track is None:
            track = self._pick_next_track()
            if track is not None:
                self._play_track(track)

    @classmethod
    def _should_run(cls):
        return True

    @classmethod
    def _run_generator(cls, fn, delay=0):
        threading.Timer(delay, fn).start()

    def _generate_ads(self):
        if (
            self._ads_generator is not None
            and not self._ads
            and not self._ads_generator_busy
        ):
            self._ads_generator_busy = True
            if self._device.playback_priority == "ads_over_music":
                next_track_time = get_local_time(self._device.timezone)
            else:
                # if music has higher priority then next ad should
                # be from time of next track
                next_track_time = self._next_track_draw_time or get_local_time(
                    self._device.timezone
                )
            self._ads_generator.draw_and_download(next_track_time)

    def _generate_music(self):
        if (
            self._music_generator is not None
            and not self._music
            and not self._music_generator_busy
        ):
            self._music_generator_busy = True
            next_track_time = self._next_track_draw_time or get_local_time(
                self._device.timezone
            )
            self._music_generator.draw_and_download(next_track_time)

    def _pick_next_track(self):
        pick = None
        if self._ads:
            pick = self._ads.pop(0)
        elif self._music:
            pick = self._music.pop(0)

        current_time = get_local_time(self._device.timezone)
        if pick is not None:
            self._next_track_draw_time = current_time + datetime.timedelta(
                seconds=pick["length"]
            )
            logger.debug("Picked: {}".format(pick))
        else:
            self._next_track_draw_time = current_time
        return pick

    def _play_track(self, track):
        self._current_track = track
        signal = json.dumps(
            (
                "PLAY",
                [
                    track,
                ],
            )
        )
        while not self._redis.publish(settings.PLAYER_REDIS_CHANNEL, signal):
            time.sleep(0.1)

    def _skip_track(self):
        signal = json.dumps(("SKIP", []))
        while not self._redis.publish(settings.PLAYER_REDIS_CHANNEL, signal):
            time.sleep(0.1)

    def _set_player_volume(self, val):
        signal = json.dumps(
            (
                "SET_VOLUME",
                [
                    val,
                ],
            )
        )
        while not self._redis.publish(settings.PLAYER_REDIS_CHANNEL, signal):
            time.sleep(0.1)

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

    @property
    def _ack_sync_url(self):
        return "{}/api/devices/{}/ack-sync/".format(
            settings.APP_URL,
            settings.DEVICE_ID,
        )

    @property
    def _ack_play_url(self):
        return "{}/api/devices/{}/ack-play/".format(
            settings.APP_URL,
            settings.DEVICE_ID,
        )

    # local signals
    def _on_player_ready(self):
        logger.debug("Received PLAYER_READY signal")
        self._player_ready = True
        self._set_player_volume(self._device.volume)

    def _on_player_idle(self):
        """
        Inform scheduler that player is ready and no track is playing,
        this prevents cases when player was restarted and scheduler
        current track is not None,
        main loop will then pick next track.
        """
        logger.debug("Received PLAYER_IDLE signal")
        self._player_ready = True
        self._current_track = None
        self._next_track_draw_time = None
        if self._player_idle is not True:
            self._player_idle = True

    def _on_track_play(self, track) -> None:
        current_time = get_local_time(self._device.timezone)
        logger.debug(
            "Player started track: {} at: {}".format(track, current_time)
        )
        self._player_idle = False

        # ack play on remote server
        payload = {
            "id": track["id"],
            "track_type": track["track_type"],
            "timestamp": current_time,
        }
        response = client.make_request(
            self._ack_play_url, "post", data=payload
        )
        logger.debug("Ack play finished with response: {}".format(response))

    def _on_track_finished(self, track) -> None:
        logger.debug("Finished playing {}".format(track))
        self._current_track = None

    def _on_ad_track_download(self, track) -> None:
        logger.debug(
            "Downloaded track: {}," " adding to ads playlist".format(track)
        )
        self._ads.append(track)

    def _on_music_track_download(self, track) -> None:
        logger.debug(
            "Downloaded track: {}, adding to music playlist".format(track)
        )
        self._music.append(track)

    def _on_music_track_download_failure(self, track) -> None:
        logger.debug("Failed to download track: {}".format(track))

    def _on_device_sync(self) -> None:
        logger.debug("Received DEVICE_SYNC signal")
        self._ads = []
        self._music = []
        self._ads_generator = AdBlockBasedGenerator(self._device)
        self._music_generator = MusicBlockBasedGenerator(self._device)
        self._set_player_volume(self._device.volume)
        self._skip_track()  # let scheduler draw new track
        self._last_device_sync = get_local_time(self._device.timezone).date()
        # ack sync on remote server
        client.make_request(self._ack_sync_url, "post")

    def _on_ads_generator_finish(self) -> None:
        self._ads_generator_busy = False

    def _on_music_generator_finish(self) -> None:
        self._music_generator_busy = False
