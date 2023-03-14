import vlc

from soundfleet_player.types import AudioTrack


class MediaBackend:
    def __init__(self) -> None:
        self._player = vlc.MediaPlayer()

    def play(self, track: AudioTrack):
        self._player.set_media(vlc.Media(track["uri"]))
        self._player.play()

    def stop(self) -> None:
        self._player.stop()

    def is_playing(self) -> bool:
        return self._player.is_playing()

    def set_volume(self, value: int) -> None:
        value = min(max(value, 0), 100)
        self._player.audio_set_volume(value)
