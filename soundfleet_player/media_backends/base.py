from typing import Protocol


from soundfleet_player.types import AudioTrack


class MediaBackend(Protocol):
    def play(self, track: AudioTrack) -> None:
        pass

    def stop(self) -> None:
        pass

    def is_playing(self) -> bool:
        pass

    def set_volume(self, value: int) -> None:
        pass
