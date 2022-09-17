import threading

from functools import partial

from soundfleet_player.types import AudioTrack


class MediaBackend:

    _is_playing = False
    _volume = 100

    def play(self, track: AudioTrack) -> None:
        self._is_playing = True
        threading.Timer(
            track["length"], partial(self._set_is_playing, False)
        ).start()

    def stop(self):
        self._set_is_playing(False)

    def is_playing(self):
        return self._is_playing

    def set_volume(self, value: int):
        self._volume = value

    def _set_is_playing(self, val: bool):
        self._is_playing = val
