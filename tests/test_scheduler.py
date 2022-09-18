import datetime
import json
from re import I

import freezegun
import pytest
import pytz
import time

from unittest import mock

from soundfleet_player.conf import settings
from soundfleet_player.scheduler import Scheduler
from soundfleet_player.utils import get_redis_conn
from .utils import ExitAfter, is_redis_running


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@pytest.mark.parametrize(
    ["ads", "music", "expected_pick"],
    [
        ([], [], None),
        (
            [{"id": 1, "track_type": "ad", "length": 1}],
            [],
            {"id": 1, "track_type": "ad", "length": 1},
        ),
        (
            [{"id": 1, "track_type": "ad", "length": 1}],
            [{"id": 2, "track_type": "music", "length": 1}],
            {"id": 1, "track_type": "ad", "length": 1},
        ),
        (
            [],
            [{"id": 2, "track_type": "music", "length": 1}],
            {"id": 2, "track_type": "music", "length": 1},
        ),
    ],
)
@mock.patch("soundfleet_player.scheduler.Device")
@mock.patch("soundfleet_player.scheduler.client.make_request")
def test_pick_next_track(_, device, ads, music, expected_pick):
    class MyDevice:
        @property
        def timezone(self):
            return pytz.UTC

        @property
        def playback_mode(self):
            return "calendar"

        @property
        def playback_priority(self):
            return "music_over_ads"

        @property
        def stream(self):
            return None

    device.return_value = MyDevice()
    scheduler = Scheduler()
    scheduler._music.extend(ads)
    scheduler._music.extend(music)
    pick = scheduler._pick_next_track()
    assert pick == expected_pick


@mock.patch("soundfleet_player.scheduler.get_and_decode_redis_message")
@mock.patch("soundfleet_player.scheduler.Scheduler._should_run")
@mock.patch("soundfleet_player.scheduler.Device")
def test_on_player_ready_is_called(device, should_run, get_msg):
    class MyDevice:
        @property
        def timezone(self):
            return pytz.UTC

        @property
        def playback_mode(self):
            return "calendar"

        @property
        def playback_priority(self):
            return "music_over_ads"

        def sync(self):
            pass

        @property
        def stream(self):
            return None

    device.return_value = MyDevice()
    should_run.side_effect = ExitAfter(1)
    get_msg.return_value = ("PLAYER_READY", [])
    scheduler = Scheduler()
    assert not scheduler._player_ready
    scheduler.run()
    assert scheduler._player_ready


@mock.patch("soundfleet_player.scheduler.get_and_decode_redis_message")
@mock.patch("soundfleet_player.scheduler.Scheduler._should_run")
@mock.patch("soundfleet_player.scheduler.Device")
def test_on_player_idle(device, should_run, get_msg):
    class MyDevice:
        @property
        def timezone(self):
            return pytz.UTC

        @property
        def playback_mode(self):
            return "calendar"

        @property
        def playback_priority(self):
            return "music_over_ads"

        def sync(self):
            pass

        @property
        def stream(self):
            return None

    device.return_value = MyDevice()
    should_run.side_effect = ExitAfter(1)
    get_msg.return_value = ("PLAYER_IDLE", [])
    scheduler = Scheduler()
    setattr(scheduler, "_player_ready", False)
    setattr(scheduler, "_current_track", "some_track")
    setattr(scheduler, "_next_track_draw_time", "some_time")
    dt = datetime.datetime.now()
    with freezegun.freeze_time(dt):
        scheduler.run()
        dt = datetime.datetime.utcnow().replace(tzinfo=pytz.UTC)  # frozen dt
        assert scheduler._player_ready
        assert scheduler._current_track is None
        assert scheduler._next_track_draw_time == dt


@pytest.mark.parametrize(
    ["loops", "expected_calls"],
    [
        (1, 0),
        (9, 0),
        (10, 2),
        (11, 2),
        (19, 2),
        (20, 4),
    ],
)
@mock.patch("soundfleet_player.scheduler.threading.Thread.start")
@mock.patch("soundfleet_player.scheduler.Scheduler._should_run")
@mock.patch("soundfleet_player.scheduler.Device")
def test_generators_are_started_every_1_second(
    device, should_run, thread_start, loops, expected_calls
):
    class MyDevice:
        @property
        def timezone(self):
            return pytz.UTC

        @property
        def playback_priority(self):
            return "music_over_ads"

        @property
        def playback_mode(self):
            return "calendar"

        def sync(self):
            pass

        @property
        def stream(self):
            return None

    device.return_value = MyDevice()
    should_run.side_effect = ExitAfter(loops)
    scheduler = Scheduler()
    scheduler.run()
    assert thread_start.call_count == expected_calls


@mock.patch(
    "soundfleet_player.scheduler.AdBlockBasedGenerator.draw_and_download"
)
@mock.patch(
    "soundfleet_player.scheduler.MusicBlockBasedGenerator.draw_and_download"
)
@mock.patch("soundfleet_player.scheduler.Scheduler._run_generator")
@mock.patch("soundfleet_player.scheduler.Scheduler._should_run")
@mock.patch("soundfleet_player.scheduler.Device")
def test_ads_and_music_generator_is_called_when_it_should(
    device, should_run, run_generator, draw_music, draw_ads
):
    class MyDevice:
        @property
        def timezone(self):
            return pytz.UTC

        @property
        def playback_priority(self):
            return "music_over_ads"

        @property
        def playback_mode(self):
            return "calendar"

        def sync(self):
            signal = json.dumps(("DEVICE_SYNC", []))
            r = get_redis_conn(host="redis")
            while not r.publish(settings.SCHEDULER_REDIS_CHANNEL, signal):
                time.sleep(0.1)

        @property
        def stream(self):
            return None

    device.return_value = MyDevice()
    should_run.side_effect = ExitAfter(10)
    run_generator.side_effect = lambda fn, *args: fn()
    scheduler = Scheduler()
    scheduler.run()
    assert draw_ads.called
    assert draw_music.called
