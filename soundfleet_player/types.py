import datetime

from typing import Literal, TypedDict


class AudioTrack(TypedDict):
    id: int
    file: str
    track_type: Literal["music", "ad"]
    length: int
    size: int
    url: str


class MusicBlock(TypedDict):
    id: int
    start: datetime.time
    end: datetime.time
    tracks: list[int]


class AdBlock(TypedDict):
    id: int
    start: datetime.time
    end: datetime.time
    playback_interval: int
    ads_count_per_block: int
    play_all_ads: bool
    tracks: list[int]


class Device(TypedDict):
    id: str
    timezone_name: str
    volume: int
    playback_priority: Literal["music", "ads"]


class DeviceState(TypedDict):
    device: Device
    audio_tracks: list[AudioTrack]
    music_blocks: list[MusicBlock]
    ad_blocks: list[AdBlock]
