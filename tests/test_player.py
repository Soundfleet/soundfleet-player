import json
import os
import pytest
import threading
import time

from unittest import mock

from soundfleet_player.conf import settings
from soundfleet_player.media_backends.dummy import MediaBackend
from soundfleet_player.player import Player
from soundfleet_player.utils import get_redis_conn
from .utils import ExitAfter, is_redis_running


def get_test_track_path(name):
    return os.path.join(os.path.dirname(__file__), "tracks", name)


@pytest.mark.skipif(
    not is_redis_running(host="redis"), reason="Redis is not running"
)
@mock.patch("soundfleet_player.player.Player._ack_play")
def test_play_file(ack_play):
    track = {"id": 1, "file": "1.ogg", "length": 1}

    player = Player(MediaBackend())
    assert not player._is_playing()
    player._play(track)
    assert player._is_playing()
    assert ack_play.called
    time.sleep(2)
    assert not player._is_playing()


@mock.patch("soundfleet_player.player.Player._should_run")
@mock.patch("soundfleet_player.player.Player._ack_play")
@mock.patch("soundfleet_player.player.Player._ack_ready")
@mock.patch("soundfleet_player.player.Player._ack_finish")
def test_skip(
    ack_finish,
    ack_ready,
    ack_play,
    should_run,
):
    track = {"id": 1, "file": "1.ogg", "length": 5}
    ack_play.return_value = None
    ack_ready.return_value = None
    should_run.side_effect = ExitAfter(10)

    def skip_track():
        signal = json.dumps(("SKIP", []))
        r = get_redis_conn()
        while not r.publish(settings.PLAYER_REDIS_CHANNEL, signal):
            continue

    player = Player(MediaBackend())
    player._current_track = track
    threading.Timer(0.1, skip_track).start()
    player.run()
    assert ack_finish.called
