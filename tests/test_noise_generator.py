import datetime
import math
import pytest
import pytz
import time

from unittest import mock

from soundfleet_player.cache import MusicBlocksCache, AdBlocksCache
from soundfleet_player.noise_generator import (
    MusicBlockBasedGenerator,
    AdBlockBasedGenerator,
)
from soundfleet_player.utils import get_local_time_from_time_str
from .utils import is_redis_running
from .fixtures import device


MUSIC_SCHEDULE = [
    {"id": 1, "start": "00:00:00", "end": "00:59:59", "tracks": [1]},
    {"id": 2, "start": "02:00:00", "end": "02:59:59", "tracks": [1]},
    {"id": 3, "start": "04:00:00", "end": "04:59:59", "tracks": [1]},
    {"id": 4, "start": "06:00:00", "end": "06:59:59", "tracks": [1]},
    {"id": 5, "start": "08:00:00", "end": "08:59:59", "tracks": [2]},
    {"id": 6, "start": "10:00:00", "end": "10:59:59", "tracks": [2]},
    {"id": 7, "start": "12:00:00", "end": "12:59:59", "tracks": [2]},
    {"id": 8, "start": "14:00:00", "end": "14:59:59", "tracks": [2]},
    {"id": 9, "start": "16:00:00", "end": "16:59:59", "tracks": [3]},
    {"id": 10, "start": "18:00:00", "end": "18:59:59", "tracks": [3]},
    {"id": 11, "start": "20:00:00", "end": "20:59:59", "tracks": [3]},
    {"id": 12, "start": "22:00:00", "end": "22:59:59", "tracks": [3]},
]


AD_CAMPAIGN = []


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@pytest.mark.parametrize(
    ["blocks", "time", "download_called"],
    [
        ([], get_local_time_from_time_str(pytz.UTC, "12:00:00"), False),
        (
            [
                {
                    "id": 1,
                    "start": "00:00:00",
                    "end": "23:59:59",
                    "tracks": [1, 2, 3],
                },
            ],
            get_local_time_from_time_str(pytz.UTC, "12:00:00"),
            True,
        ),
        (
            [
                {
                    "id": 1,
                    "start": "00:00:00",
                    "end": "23:59:59",
                    "tracks": [],
                },
            ],
            get_local_time_from_time_str(pytz.UTC, "12:00:00"),
            False,
        ),
    ],
)
@mock.patch(
    "soundfleet_player.noise_generator.MusicBlockBasedGenerator._download_and_ack"
)
@mock.patch(
    "soundfleet_player.noise_generator.MusicBlockBasedGenerator._notify_finished"
)
def test_draw_music(notify, download, blocks, time, download_called, device):
    cache = MusicBlocksCache()
    cache.set(blocks)
    generator = MusicBlockBasedGenerator(device)
    generator.draw_and_download(time)
    assert download.called == download_called
    assert notify.called


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@mock.patch("soundfleet_player.utils.redis.StrictRedis.publish")
@mock.patch("soundfleet_player.noise_generator.AudioTrackStorage.download")
def test_download_and_ack(download, publish, device):
    class MyPublish:
        def __init__(self):
            self.publish_values = iter([0, 1])

        def __call__(self, *args, **kwargs):
            return next(self.publish_values)

    download.return_value = {"id": 1}
    publish.side_effect = MyPublish()

    generator = MusicBlockBasedGenerator(device)
    generator._download_and_ack({"id": 1})
    assert download.called
    assert publish.call_count == 2


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@mock.patch("soundfleet_player.utils.redis.StrictRedis.publish")
def test_notify_finished(publish, device):
    class MyPublish:
        def __init__(self):
            self.publish_values = iter([0, 1])

        def __call__(self, *args, **kwargs):
            return next(self.publish_values)

    publish.side_effect = MyPublish()

    generator = MusicBlockBasedGenerator(device)
    generator._notify_finished()
    assert publish.call_count == 2


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@pytest.mark.parametrize(
    ["time", "call_args"],
    [
        (
            get_local_time_from_time_str(pytz.UTC, "{}:59:59".format(h)),
            {"id": int(h / 8)} if h % 2 == 0 else None,
        )
        for h in range(24)
    ],
)
@mock.patch(
    "soundfleet_player.noise_generator.MusicBlockBasedGenerator._download_and_ack"
)
@mock.patch(
    "soundfleet_player.noise_generator.MusicBlockBasedGenerator._notify_finished"
)
def test_draw_from_correct_block(notify, download, time, call_args, device):
    device._music_blocks_cache.set(MUSIC_SCHEDULE)
    generator = MusicBlockBasedGenerator(device)
    generator.draw_and_download(time)
    assert notify.called
    if call_args:
        assert download.called_with(*call_args)
    else:
        assert not download.called


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@mock.patch(
    "soundfleet_player.noise_generator.MusicBlockBasedGenerator._download_and_ack"
)
@mock.patch(
    "soundfleet_player.noise_generator.MusicBlockBasedGenerator._notify_finished"
)
def test_draw_music_performance(notify, download, device):
    tracks = [
        {"id": i, "file": "{}.ogg".format(i), "length": 1} for i in range(5000)
    ]
    blocks = [
        {
            "id": 1,
            "start": "00:00:00",
            "end": "23:59:59",
            "tracks": [i for i in range(5000)],
        },
    ]
    device._audio_tracks_cache.update(tracks)
    device._music_blocks_cache.set(blocks)
    generator = MusicBlockBasedGenerator(device)
    t = time.time()
    generator.draw_and_download(
        get_local_time_from_time_str(pytz.UTC, "12:00:00")
    )
    assert time.time() - t <= 1


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@pytest.mark.parametrize(
    ["blocks", "time", "download_called"],
    [
        ([], get_local_time_from_time_str(pytz.UTC, "12:00:00"), False),
        (
            [
                {
                    "id": 1,
                    "start": "00:00:00",
                    "end": "23:59:59",
                    "ads_count_per_block": 1,
                    "play_all_ads": True,
                    "playback_interval": 5,
                    "tracks": [1],
                },
            ],
            get_local_time_from_time_str(pytz.UTC, "12:00:00"),
            True,
        ),
        (
            [
                {
                    "id": 1,
                    "start": "00:00:00",
                    "end": "23:59:59",
                    "ads_count_per_block": 1,
                    "play_all_ads": True,
                    "playback_interval": 5,
                    "tracks": [],
                },
            ],
            get_local_time_from_time_str(pytz.UTC, "12:00:00"),
            False,
        ),
    ],
)
@mock.patch(
    "soundfleet_player.noise_generator.AdBlockBasedGenerator._download_and_ack"
)
@mock.patch(
    "soundfleet_player.noise_generator.AdBlockBasedGenerator._notify_finished"
)
def test_draw_ads(notify, download, blocks, time, download_called, device):
    cache = AdBlocksCache()
    cache.set(blocks)
    generator = AdBlockBasedGenerator(device)
    generator.draw_and_download(time)
    assert notify.called
    assert download.called == download_called


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@pytest.mark.parametrize(
    ["playback_interval"],
    [
        (5,),
        (10,),
        (15,),
        (30,),
        (60,),
    ],
)
@mock.patch(
    "soundfleet_player.noise_generator.AdBlockBasedGenerator._download_and_ack"
)
@mock.patch(
    "soundfleet_player.noise_generator.AdBlockBasedGenerator._notify_finished"
)
def test_draw_ads_are_called_with_correct_interval(
    _, download, playback_interval, device
):
    blocks = [
        {
            "id": 1,
            "start": "00:00:00",
            "end": "23:59:59",
            "ads_count_per_block": 1,
            "play_all_ads": True,
            "playback_interval": playback_interval,
            "tracks": [1],
        },
    ]
    seconds = playback_interval * 60 + 1  # track of id=1 duration is 1s
    seconds_in_day = 24 * 60 * 60
    cache = AdBlocksCache()
    cache.set(blocks)
    generator = AdBlockBasedGenerator(device)
    start = get_local_time_from_time_str(pytz.UTC, "00:00:00")
    while start < get_local_time_from_time_str(pytz.UTC, "23:59:59"):
        generator.draw_and_download(start)
        start += datetime.timedelta(seconds=60)
    assert download.call_count == math.ceil(seconds_in_day / seconds)


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@mock.patch("soundfleet_player.utils.redis.StrictRedis.publish")
@mock.patch("soundfleet_player.noise_generator.AudioTrackStorage.download")
def test_download_and_ack(download, publish, device):
    class MyPublish:
        def __init__(self):
            self.publish_values = iter([0, 1])

        def __call__(self, *args, **kwargs):
            return next(self.publish_values)

    download.return_value = {"id": 1}
    publish.side_effect = MyPublish()

    generator = AdBlockBasedGenerator(device)
    generator._download_and_ack({"id": 1})
    assert download.called
    assert publish.call_count == 2


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@mock.patch("soundfleet_player.utils.redis.StrictRedis.publish")
def test_notify_finished(publish, device):
    class MyPublish:
        def __init__(self):
            self.publish_values = iter([0, 1])

        def __call__(self, *args, **kwargs):
            return next(self.publish_values)

    publish.side_effect = MyPublish()

    generator = AdBlockBasedGenerator(device)
    generator._notify_finished()
    assert publish.call_count == 2


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@mock.patch(
    "soundfleet_player.noise_generator.AdBlockBasedGenerator._download_and_ack"
)
@mock.patch(
    "soundfleet_player.noise_generator.AdBlockBasedGenerator._notify_finished"
)
def test_draw_ads_performance(notify, download, device):
    """
    Draw 100 ads from base of 50k ads, this should not exceed 1s
    """
    tracks = [
        {"id": i, "file": "{}.ogg".format(i), "length": 1} for i in range(5000)
    ]
    blocks = [
        {
            "id": 1,
            "start": "00:00:00",
            "end": "23:59:59",
            "ads_count_per_block": 100,
            "play_all_ads": False,
            "playback_interval": 5,
            "tracks": [i for i in range(5000)],
        },
    ]
    device._audio_tracks_cache.update(tracks)
    device._ad_blocks_cache.set(blocks)
    generator = AdBlockBasedGenerator(device)
    t = time.time()
    generator.draw_and_download(
        get_local_time_from_time_str(pytz.UTC, "12:00:00")
    )
    assert time.time() - t <= 1
